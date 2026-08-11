import os
import csv
import re


ASSET_CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "device_assests",
    "Asset Management - Sheet1.csv"
)


ALLOWED_APPS_CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "device_assests",
    "Allowed_Applications.csv"
)


def lookup_asset_by_identifier(identifier: str) -> dict | None:
    """Looks up a device asset record from Asset Management - Sheet1.csv by email or emp_id.

    Returns dict with keys:
        emp_id, employee_name, email, device_id, target_os, hostname (DV_IP)
    or None if no match found.
    """
    if not identifier or not os.path.exists(ASSET_CSV_PATH):
        return None

    clean_id = str(identifier).strip().lower()

    try:
        with open(ASSET_CSV_PATH, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Standardize keys (strip whitespace from headers)
                clean_row = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}

                emp_id = clean_row.get("EMP_ID", "").strip().lower()
                emp_mail = clean_row.get("EMP_MAIL", "").strip().lower()

                if clean_id == emp_id or clean_id == emp_mail:
                    os_raw = clean_row.get("DV_OS", "windows").lower()
                    target_os = "windows" if "win" in os_raw else "linux" if "linux" in os_raw else "macos"

                    return {
                        "emp_id": clean_row.get("EMP_ID", "").strip(),
                        "employee_name": clean_row.get("EMP_NAME", "").strip(),
                        "email": clean_row.get("EMP_MAIL", "").strip(),
                        "device_id": clean_row.get("DV_ID", "").strip(),
                        "target_os": target_os,
                        "hostname": clean_row.get("DV_IP", "").strip(),  # Target IP for pywinrm
                        "username": clean_row.get("DV_USER", "").strip(),
                        "password": clean_row.get("DV_PASS", "").strip(),
                    }
    except Exception as e:
        print(f"[Warning] Asset lookup failed for {identifier}: {e}")

    return None


def is_application_allowed(emp_id: str, app_or_exe: str) -> bool:
    """Checks if an app or executable is approved in Allowed_Applications.csv for emp_id."""
    if not emp_id or not app_or_exe or not os.path.exists(ALLOWED_APPS_CSV_PATH):
        return True  # Fallback to allowed if CSV is missing

    clean_emp = str(emp_id).strip().lower()
    clean_target = str(app_or_exe).strip().lower()
    clean_target_no_ext = clean_target.rsplit(".", 1)[0] if "." in clean_target else clean_target

    try:
        with open(ALLOWED_APPS_CSV_PATH, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                clean_row = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k and v}
                row_emp = clean_row.get("EMP_ID", "").strip().lower()
                app_name = clean_row.get("ALLOWED_APP_NAME", "").strip().lower()
                exe_name = clean_row.get("ALLOWED_EXECUTABLE", "").strip().lower()
                status = clean_row.get("POLICY_STATUS", "").strip().lower()

                row_values_lower = [str(v).strip().lower() for v in row.values() if v]

                if row_emp == clean_emp:
                    # Check if target matches app_name, exe_name, or any field in the row
                    matches_target = (
                        clean_target in app_name or clean_target in exe_name or
                        app_name in clean_target or exe_name in clean_target or
                        clean_target_no_ext in app_name or clean_target_no_ext in exe_name or
                        any(clean_target in val or clean_target_no_ext in val for val in row_values_lower)
                    )

                    is_approved = status == "approved" or "approved" in row_values_lower

                    if matches_target and is_approved:
                        return True
    except Exception as e:
        print(f"[Warning] Allowed applications lookup failed: {e}")

    return False


def extract_and_lookup_asset(ticket_raw: str, existing_entities: dict = None) -> dict:
    """Extracts email or emp_id from ticket text or existing_entities and resolves asset details.

    Returns enriched entities dict.
    """
    entities = dict(existing_entities) if existing_entities else {}

    # 1. Try lookup from existing entities
    search_keys = ["email", "emp_id", "employee_id"]
    for key in search_keys:
        val = entities.get(key)
        if val:
            asset = lookup_asset_by_identifier(val)
            if asset:
                entities.update(asset)
                print(f"[AssetLookup] Found asset for {key}='{val}': {asset}")
                return entities

    # 2. Extract email from ticket_raw via regex
    if ticket_raw:
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", ticket_raw)
        if email_match:
            email = email_match.group(0)
            asset = lookup_asset_by_identifier(email)
            if asset:
                entities.update(asset)
                print(f"[AssetLookup] Found asset for extracted email '{email}': {asset}")
                return entities

        # Extract emp_id (e.g. EL-001, EL-002)
        emp_match = re.search(r"\bEL-\d{3}\b", ticket_raw, re.IGNORECASE)
        if emp_match:
            emp_id = emp_match.group(0).upper()
            asset = lookup_asset_by_identifier(emp_id)
            if asset:
                entities.update(asset)
                print(f"[AssetLookup] Found asset for extracted emp_id '{emp_id}': {asset}")
                return entities

    # Fallback default if not found
    if "hostname" not in entities:
        print(f"[AssetLookup] No matching asset found in CSV. Using fallback.")

    return entities

