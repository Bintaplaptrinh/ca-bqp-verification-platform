export interface CurrentUser {
  subject: string;
  username: string;
  displayName: string;
  isAdmin: boolean;
  /** Effective permissions, for rendering only — the server re-checks each request. */
  permissions: Set<string>;
  coverageGroups: Set<string>;
  mustChangePassword: boolean;
  /** Derived projection the backend also sends; kept for display labels. */
  roles: Set<string>;
}
