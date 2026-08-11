# Logins Playbooks Catalog

- [Disable MFA for a User](./SOP-AUTH-006-001.md) - Disables Multi-Factor Authentication (MFA) for a user account after confirmed request, requiring the user's current password for security confirmation.
- [Handle Suspicious Login Report](./SOP-AUTH-007-001.md) - Procedure to lock a user account and escalate to security team upon receiving a suspicious login report. Includes steps to review audit logs and prevent further access during investigation.
- [Find User Account with Partial Details](./SOP-AUTH-009-001.md) - Search for a user account using partial details (e.g., partial email, name) to identify the correct account before proceeding with further actions.
- [Unlock a User's Account](./SOP-auth-001-001.md) - Automated playbook to search for a locked user account, verify lock status, and unlock the account if it is a standard lockout. Escalates if the account is locked for security review.
- [Admin-Assisted User Password Reset](./SOP-auth-003-001.md) - Admin procedure to reset a user's password when self-service methods fail. Includes account verification, temporary password generation, and secure delivery instructions.
- [Reset User's MFA Device](./SOP-auth-004-001.md) - Automated playbook to reset a user's MFA device in the L1 Support Platform when they lose access to their authenticator app. Verifies account existence, checks current MFA status, and performs MFA reset if enabled.
