# Authentication and authorization

## Authentication: who you are
- Email magic link
- Google sign-in

Options:
- Verify the email address
- Slow down and lock out after failed sign-ins
- Two-factor sign-in for owners and admins
- Use a proven library or auth service; never store a password yourself.
- Sessions are secure, HTTP-only cookies; sign-out ends the session on the server.

## Authorization: what you may do
- Deny by default: a route with no rule below is refused.
- Check the permission on the server, on every request; pages only hide what the server already refuses.
- Tenants: One database, tenant id on every row and key. Every row and key carries the tenant id, and every query filters by it. This is always on.

| Permission | Registered user | Pharmacist/health care professional | Guest User | System Administrator |
|---|---|---|---|---|
| barcode scanner | yes | — | — | — |
| Medicine Information Lookup | yes | — | — | — |
| Medicines details page | yes | — | — | — |
| Manage team and roles | yes | — | — | — |
| Billing and plan | yes | — | — | — |
| Business settings | yes | — | — | — |
| Usage and logs | yes | — | — | — |
| Export data | yes | — | — | — |

Options:
- None
