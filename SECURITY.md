# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in **JS Radar**, please **do not silently discard it** — responsible disclosure helps protect all users.

### How to Report

Open a **GitHub Issue** in this repository using the following guidelines:

1. **Title**: Start with `[SECURITY]` followed by a short description.
   - Example: `[SECURITY] Unauthenticated access to scan results via IDOR`

2. **Issue Body** must include:

   #### Vulnerability Summary
   A brief description of the vulnerability, its type (e.g., IDOR, SSRF, XSS, RCE, Auth Bypass, etc.), and its potential impact.

   #### Affected Component
   Specify which part of the system is affected (e.g., REST API, frontend, scanner worker, authentication layer, Docker deployment, etc.).

   #### Proof of Concept (POC)
   Provide a clear, reproducible demonstration of the vulnerability. Include:
   - Request/response captures (curl commands, Burp Suite screenshots, etc.)
   - Payloads used
   - Any scripts or tools involved

   #### Steps to Reproduce
   ```
   1. Start the application / access the SaaS instance
   2. Navigate to / send request to [endpoint or component]
   3. Perform [specific action]
   4. Observe [unexpected behavior or security impact]
   ```

   #### Expected vs Actual Behavior
   - **Expected**: What should happen (secure behavior)
   - **Actual**: What actually happens (vulnerable behavior)

   #### Severity Assessment
   Rate the severity using CVSS or a simple scale:
   - Critical / High / Medium / Low / Informational

   #### Suggested Fix (Optional)
   If you have a recommendation for how to remediate the issue, include it here.

---

### Response

All valid security issues reported will be:

- Acknowledged and triaged
- Fixed in a reasonable timeframe based on severity
- Credited to the reporter (unless anonymity is requested)

Thank you for helping keep JS Radar and its users safe.
