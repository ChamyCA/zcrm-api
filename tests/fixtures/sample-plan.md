# Sample plan: account, contact, cleanup

Prose here is never executed. Only the header and step blocks are parsed.

```zcrm-plan
org_id: "5725767000000012345"
title: Sample plan
```

### s1 — Check existing modules

```zcrm-step
method: GET
path: /settings/modules
```

### s2 — Create the account

```zcrm-step
method: POST
path: /Accounts
body:
  data:
    - Account_Name: Acme Demo
capture:
  account_id: data[0].details.id
```

### s3 — Create a contact on the account

```zcrm-step
method: POST
path: /Contacts
body:
  data:
    - Last_Name: Smith
      Account_Name:
        id: "{{account_id}}"
depends_on: [s2]
```

### s4 — Delete the account again

```zcrm-step
method: DELETE
path: /Accounts/{{account_id}}
depends_on: [s3]
```
