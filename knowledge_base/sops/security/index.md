# Security Playbooks Catalog

- [Phishing Incident Host Isolation & Perimeter Domain Block](./SOP-SOC-016.md) | Platform: `system` | Triggers: `phishing, containment, isolation, firewall, azuread, dns, soc` | Automated playbook for rapid containment of compromised endpoints involved in phishing incidents, including host isolation, perimeter domain blocking, user session revocation, and DNS cache flushing. This playbook orchestrates actions from a Windows PowerShell environment, targeting both Windows endpoints and Linux-based network devices via SSH.
