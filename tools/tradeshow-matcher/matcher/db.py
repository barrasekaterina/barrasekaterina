"""Optional live pull of CRM Contacts/Leads straight from the Bitrix CRM
database, as an alternative to uploading the CSV exports.

Both queries authenticate via Windows Integrated Auth (Trusted_Connection) -
no username/password is needed or accepted. This only works from a
domain-joined Windows machine (or a Linux box configured for Kerberos
against that domain) logged in as an account with access to the CRM
database - it will not work from an arbitrary Linux container, which is why
this module needs network access to the internal admortgage BI server and
the "ODBC Driver 17 for SQL Server" installed, neither of which is
available in this sandbox. The two fetch_* functions below have therefore
only been validated against a mocked DataFrame shaped like the expected
query output (see sample_data/smoke_test_db.py) through
standardize_db_contacts / standardize_db_leads in loaders.py, not against a
live database.
"""
from __future__ import annotations

import os

import pandas as pd

CONTACTS_QUERY = """
DECLARE @today DATE = CAST(GETDATE() AS DATE),
        @StartOfMonth DATE = DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()), 0);

WITH observers AS (
    SELECT
        contact.ID AS CONTACT_ID,
        STRING_AGG(obs_co.USER_ID, ', ') AS OBSERVER_ID,
        STRING_AGG(usr.NAME + ' ' + usr.LAST_NAME, ', ') AS OBSERVER_NAME
    FROM [crm].[dbo].b_crm_contact AS contact
    JOIN crm.dbo.b_crm_observer AS obs_co
        ON obs_co.ENTITY_TYPE_ID = 3
       AND obs_co.ENTITY_ID = contact.ID
    JOIN crm.dbo.b_user AS usr
        ON usr.ID = obs_co.USER_ID
    GROUP BY contact.ID
),

emails AS (
    SELECT
        fm.ELEMENT_ID,
        STRING_AGG(fm.VALUE, ', ') AS Emails
    FROM crm.dbo.b_crm_field_multi AS fm
    WHERE fm.TYPE_ID = 'EMAIL'
      AND fm.ENTITY_ID = 'CONTACT'
    GROUP BY fm.ELEMENT_ID
),

phones AS (
    SELECT
        fm.ELEMENT_ID,
        STRING_AGG(fm.VALUE, ', ') AS Phones
    FROM crm.dbo.b_crm_field_multi AS fm
    WHERE fm.TYPE_ID = 'PHONE'
      AND fm.ENTITY_ID = 'CONTACT'
    GROUP BY fm.ELEMENT_ID
),

contact_categories AS (
    SELECT
        ucont.VALUE_ID AS CONTACT_ID,
        STRING_AGG(enum_cat.VALUE, ', ') AS ContactCategory
    FROM [crm].[dbo].b_uts_crm_contact AS ucont
    LEFT JOIN [crm].[dbo].b_user_field_enum AS enum_cat
        ON ucont.UF_CONTACT_CATEGORIES LIKE
           '%i:' + CAST(enum_cat.ID AS VARCHAR(20)) + ';%'
    GROUP BY ucont.VALUE_ID
)

SELECT
        cont.ID AS iBitrix_Contact_ID,
        cont.NAME AS First_Name,
        cont.LAST_NAME AS Last_Name,
        ucont.UF_Z_NMLS_CONTACT AS iBitrix_Contact_NMLS_raw,
        fn_contact_status.VALUE AS ContactStatus,
        CASE TRY_CAST(ucont.UF_CONTACT_NMLS_STATUS AS INT)
            WHEN 123247 THEN 'Active'
            WHEN 123248 THEN 'Inactive'
            WHEN 123249 THEN 'Not Found'
            ELSE NULL
        END AS NMLS_Status,
        CASE TRY_CAST(ucont.UF_CONTACT_EMPLOYMENT AS INT)
            WHEN 123240 THEN 'Current'
            WHEN 123241 THEN 'Changed'
            ELSE NULL
        END AS Employment,
        cat.ContactCategory,
        bcrm.ID AS ID_Comp,
        emails.Emails AS sEmail,
        phones.Phones AS sPhone,
        usr.NAME AS AE_First_Name,
        usr.LAST_NAME AS AE_Last_Name,
        obs.OBSERVER_NAME AS Observers_name,
        bcrm.TITLE AS CompanyName,
        TRY_CAST(bucrm.UF_CRM_6225F0F2C2D28 AS INT) AS iCompany_NMLS,
        NULL AS sRole,
        bucrm.UF_CRM_COMPANY_ID AS PortalDomain,
        CAST(bucrm.UF_Z_BROKER_PACKAGE_ACCOUNTS AS DATE) AS dBP_signed,
        fn_statusB.VALUE AS BitrixStatus,
        bucrm.UF_FUNDED_12 AS iBirix_Funded_12_$,
        bucrm.UF_FUNDED_12_UNIT AS iBirix_Funded_12_units,
        bucrm.UF_Z_ACTIVE_MLO_LOCATION AS Location_State,
        NULL AS iBitrix_volume_12_$,
        bucrm.UF_VOLUME_12 AS iBitrix_volume_12_units,
        bucrm.UF_Z_LAST_SUB_DATE_ACCOUNTS AS dLast_Submission_Date,
        DATEDIFF(DAY, bucrm.UF_Z_LAST_FUNDED_DATE_ACCOUNTS, @today) AS Days_from_Last_Submission_Date,
        bucrm.UF_Z_LAST_FUNDED_DATE_ACCOUNTS AS dLast_Funding_Date
FROM [crm].[dbo].b_crm_contact AS cont
LEFT JOIN [crm].[dbo].b_uts_crm_contact AS ucont ON cont.ID = ucont.VALUE_ID
LEFT JOIN [crm].[dbo].b_user_field_enum AS fn_contact_status
    ON TRY_CAST(ucont.UF_STATUS_CONTACT AS INT) = fn_contact_status.ID
LEFT JOIN contact_categories AS cat ON cat.CONTACT_ID = cont.ID
LEFT JOIN [crm].[dbo].[b_crm_company] AS bcrm ON bcrm.ID = cont.COMPANY_ID
LEFT JOIN emails ON emails.ELEMENT_ID = cont.ID
LEFT JOIN phones ON phones.ELEMENT_ID = cont.ID
LEFT JOIN [crm].[dbo].b_uts_crm_company AS bucrm ON bucrm.VALUE_ID = bcrm.ID
LEFT JOIN [crm].[dbo].b_user_field_enum AS fn_status ON bucrm.UF_ACCOUNT_TYPE = fn_status.ID
LEFT JOIN [crm].[dbo].b_user_field_enum AS fn_statusB ON bucrm.UF_STATUS_STAGE = fn_statusB.ID
LEFT JOIN [crm].[dbo].b_user AS usr ON usr.ID = cont.ASSIGNED_BY_ID
LEFT JOIN observers AS obs ON obs.CONTACT_ID = cont.ID
WHERE
    LTRIM(RTRIM(ISNULL(ucont.UF_Z_NMLS_CONTACT, ''))) <> ''
    AND LOWER(LTRIM(RTRIM(ucont.UF_Z_NMLS_CONTACT))) NOT IN
        ('0', '00', '000', '0000', 'nan', 'none', 'null', '<na>', 'n/a', 'na')
    AND REPLACE(LTRIM(RTRIM(ucont.UF_Z_NMLS_CONTACT)), '0', '') <> '';
"""

LEADS_QUERY = """
WITH emails AS (
    SELECT
        fm.ELEMENT_ID,
        STRING_AGG(fm.[VALUE], ', ') AS Email
    FROM crm.dbo.b_crm_field_multi AS fm
    WHERE fm.ENTITY_ID = 'LEAD'
      AND fm.TYPE_ID = 'EMAIL'
    GROUP BY fm.ELEMENT_ID
),
phones AS (
    SELECT
        fm.ELEMENT_ID,
        STRING_AGG(fm.[VALUE], ', ') AS Phone
    FROM crm.dbo.b_crm_field_multi AS fm
    WHERE fm.ENTITY_ID = 'LEAD'
      AND fm.TYPE_ID = 'PHONE'
    GROUP BY fm.ELEMENT_ID
)
SELECT
    c.TITLE,
    CONCAT(u.NAME, ' ', u.LAST_NAME) AS AE,
    c.COMPANY_TITLE,
    h.UF_LEAD_COMPANY AS LC_ID,
    h.UF_Z_NMLS AS MLO_NMLS,
    h.UF_Z_COMPANY_NMLS AS COMPANY_NMLS,
    CASE h.UF_NMLS_STATUS
        WHEN 123247 THEN 'Active'
        WHEN 123248 THEN 'Inactive'
        WHEN 123249 THEN 'Not Found'
        ELSE NULL
    END AS NMLS_STATUS,
    CASE h.UF_LEAD_EMPLOYMENT
        WHEN 123245 THEN 'Current'
        WHEN 123246 THEN 'Changed'
        ELSE NULL
    END AS EMPLOYMENT_STATUS,
    e.Email,
    p.Phone,
    h.UF_LEAD_A_PHONES AS [Additional Phones],
    h.UF_LEAD_A_EMAILS AS [Additional Emails],
    c.ID AS LEAD_ID,
    c.STATUS_ID AS STAGE_ID,
    CASE c.STATUS_ID
        WHEN 'NEW' THEN 'New'
        WHEN 'UC_STARTED' THEN 'Started'
        WHEN 'UC_MARKETING' THEN 'Marketing'
        WHEN 'PREPARATION' THEN 'Preparation'
        WHEN 'CLIENT' THEN 'Client'
        WHEN 'UC_QV62RS' THEN 'QV62RS'
        WHEN 'UC_BP_SENT' THEN 'BP Sent'
        WHEN 'UC_BP_FILLED' THEN 'BP Filled'
        WHEN 'UC_DEFERRED' THEN 'Deferred'
        WHEN 'SUCCESS' THEN 'Success'
        ELSE c.STATUS_ID
    END AS STAGE
FROM crm.dbo.b_crm_lead AS c
LEFT JOIN crm.dbo.b_user AS u ON u.ID = c.ASSIGNED_BY_ID
LEFT JOIN crm.dbo.b_uts_crm_lead AS h ON h.VALUE_ID = c.ID
LEFT JOIN emails AS e ON e.ELEMENT_ID = c.ID
LEFT JOIN phones AS p ON p.ELEMENT_ID = c.ID;
"""


def _connection_string(server: str, database: str) -> str:
    # Both queries authenticate via Windows Integrated Auth. The original
    # contacts script also carried UID/PWD alongside Trusted_Connection=yes,
    # but when Trusted_Connection is set the ODBC driver ignores UID/PWD
    # entirely and uses the current Windows session instead - so those
    # credentials were never actually doing anything, and asking for them
    # in the UI only invited a confusing SQL-auth login failure (18456).
    return (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={server};"
        f"DATABASE={database};"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )


def fetch_contacts(server: str | None = None, database: str = "dm01") -> pd.DataFrame:
    """Pull CRM contacts live via Windows Integrated Auth (Trusted_Connection)."""
    import pyodbc  # imported lazily: optional dependency, only needed for this path

    server = server or os.environ.get("CRM_DB_SERVER", "bi-02.prod.admortgage.com")
    conn_str = _connection_string(server, database)
    with pyodbc.connect(conn_str) as conn:
        df = pd.read_sql(CONTACTS_QUERY, conn)

    df["iBitrix_Contact_NMLS"] = pd.to_numeric(
        df["iBitrix_Contact_NMLS_raw"], errors="coerce"
    ).astype("Int64")
    df = df.drop(columns=["iBitrix_Contact_NMLS_raw"])
    return df


def fetch_leads(server: str | None = None, database: str = "crm") -> pd.DataFrame:
    """Pull CRM leads live via Windows Integrated Auth (Trusted_Connection)."""
    import pyodbc  # imported lazily: optional dependency, only needed for this path

    server = server or os.environ.get("CRM_DB_SERVER", "bi-02.prod.admortgage.com")
    conn_str = _connection_string(server, database)
    with pyodbc.connect(conn_str) as conn:
        return pd.read_sql(LEADS_QUERY, conn)
