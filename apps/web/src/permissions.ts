/**
 * Permission codes, mirroring the server catalog in
 * `apps/backend/src/cabqp/modules/auth/permissions.py`.
 *
 * These drive what the UI offers. They do not drive what it is allowed to do:
 * the server holds the catalog and checks it per request, so a code added here
 * that the server does not know simply never matches anything.
 */
export const P = {
  CASE_CREATE: "CASE_CREATE",
  CASE_BULK: "CASE_BULK",
  CASE_VIEW_ALL: "CASE_VIEW_ALL",
  CASE_EXPORT: "CASE_EXPORT",
  LOOKUP_UNIT: "LOOKUP_UNIT",
  REVIEW_QUEUE: "REVIEW_QUEUE",
  REVIEW_DECIDE: "REVIEW_DECIDE",
  REGISTRY_ADMIN: "REGISTRY_ADMIN",
  PERSON_REGISTRY_ADMIN: "PERSON_REGISTRY_ADMIN",
  AUDIT_VIEW: "AUDIT_VIEW",
  USER_ADMIN: "USER_ADMIN",
} as const;

export type PermissionCode = (typeof P)[keyof typeof P];
