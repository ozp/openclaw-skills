# Gateways, Organizations & Users

Manage gateway connections, organization membership, and user profiles.

---

## 1. Gateway CRUD

Gateways represent OpenClaw gateway instances connected to MC. Each gateway has a main agent auto-provisioned on creation.

### Endpoints (Admin)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/gateways` | List gateways |
| `POST` | `/api/v1/gateways` | Create gateway + provision main agent |
| `GET` | `/api/v1/gateways/{id}` | Get gateway |
| `PATCH` | `/api/v1/gateways/{id}` | Update gateway (re-provisions main agent) |
| `DELETE` | `/api/v1/gateways/{id}` | Delete gateway + main agent + installed skills |
| `POST` | `/api/v1/gateways/{id}/templates/sync` | Sync workspace templates to gateway agents |

### GatewayCreate
```json
{
  "url": "string (gateway URL)",
  "token": "string (gateway token)",
  "workspace_root": "string | null",
  "allow_insecure_tls": false,
  "disable_device_pairing": false
}
```

### Template Sync Options (`POST /gateways/{id}/templates/sync`)

| Query Param | Default | Purpose |
|---|---|---|
| `include_main` | true | Sync main agent templates |
| `lead_only` | false | Only sync lead agents (skip workers) |
| `reset_sessions` | false | Reset OpenClaw sessions after sync |
| `rotate_tokens` | false | Rotate agent tokens |
| `force_bootstrap` | false | Force bootstrap even if agent exists |
| `overwrite` | false | Overwrite existing workspace files |
| `board_id` | null | Scope to specific board |

---

## 2. Gateway Session Inspection

Inspect and interact with gateway sessions directly.

### Endpoints (Admin)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/gateways/status` | Gateway connectivity + session status |
| `GET` | `/api/v1/gateways/sessions` | List gateway sessions |
| `GET` | `/api/v1/gateways/sessions/{session_id}` | Get specific session |
| `GET` | `/api/v1/gateways/sessions/{session_id}/history` | Get session chat history |
| `POST` | `/api/v1/gateways/sessions/{session_id}/message` | Send message into session |
| `GET` | `/api/v1/gateways/commands` | List supported protocol methods + events |

### Session Message
```json
{
  "content": "string"
}
```

---

## 3. Organizations

Multi-tenant container. Users are members with roles (`owner`, `admin`, `member`).

### Key Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/organizations` | any user | Create org (caller becomes owner) |
| `GET` | `/api/v1/organizations/me/list` | any user | List user's orgs |
| `GET` | `/api/v1/organizations/me` | org member | Get active org |
| `POST` | `/api/v1/organizations/me/active` | org member | Set active org |
| `GET` | `/api/v1/organizations/me/members` | org member | List org members |
| `PATCH` | `/api/v1/organizations/me/members/{id}` | org admin | Update member role/access |
| `DELETE` | `/api/v1/organizations/me/members/{id}` | org admin | Remove member |
| `POST` | `/api/v1/organizations/me/invites` | org admin | Create invite |
| `GET` | `/api/v1/organizations/me/invites` | org admin | List invites |
| `POST` | `/api/v1/organizations/accept-invite` | any user | Accept invite |

### Member Roles & Access

| Role | Capabilities |
|---|---|
| `owner` | Full admin + manage members + delete org |
| `admin` | Full admin except delete org |
| `member` | Read/write based on board access rules |

### Board Access Control

- `all_boards_read=true`: member can read all boards
- `all_boards_write=true`: member can write all boards
- Per-board access: `OrganizationBoardAccess` table grants explicit read/write to specific boards
- Board access can be pre-configured in invites via `OrganizationInviteBoardAccess`

### Invite Flow

1. Admin creates invite with email, role, optional board access
2. Invite code generated (or sent via email)
3. Invitee calls `POST /organizations/accept-invite` with code
4. Member created with configured role and board access

---

## 4. Users

Self-service user profile management.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/users/me` | Get current user profile |
| `PATCH` | `/api/v1/users/me` | Update profile |
| `DELETE` | `/api/v1/users/me` | Delete account (cascades personal-only orgs) |

---

## 5. Task Custom Fields

Organization-level custom field definitions that can be bound to specific boards.

### Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/organizations/me/custom-fields` | org member | List definitions |
| `POST` | `/api/v1/organizations/me/custom-fields` | org admin | Create definition |
| `PATCH` | `/api/v1/organizations/me/custom-fields/{id}` | org admin | Update definition |
| `DELETE` | `/api/v1/organizations/me/custom-fields/{id}` | org admin | Delete (only if no task values) |

### TaskCustomFieldDefinitionCreate
```json
{
  "field_key": "string (unique in org)",
  "label": "string | null",
  "field_type": "text | number | boolean | select | date | url",
  "ui_visibility": "visible | hidden | readonly",
  "validation_regex": "string | null",
  "description": "string | null",
  "required": false,
  "default_value": "any | null",
  "board_ids": ["uuid"]
}
```

Custom fields are set on tasks via `custom_field_values` in TaskCreate/TaskUpdate payloads.

---

## Source Reference

| File | Purpose |
|---|---|
| `backend/app/api/gateways.py` | Gateway CRUD + template sync |
| `backend/app/api/gateway.py` | Session inspection + commands |
| `backend/app/api/organizations.py` | Org + member + invite management |
| `backend/app/api/users.py` | User profile + account deletion |
| `backend/app/api/task_custom_fields.py` | Custom field definitions |
| `backend/app/services/openclaw/admin_service.py` | Gateway lifecycle + provisioning |
