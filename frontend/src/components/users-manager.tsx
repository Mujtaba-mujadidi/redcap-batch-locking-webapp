"use client";

import type { FormEvent, ReactNode } from "react";
import { useDeferredValue, useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { PageHeader } from "@/components/page-header";
import { formatDate } from "@/lib/format";
import type { AuthUser, Role, UserRecord } from "@/lib/types";

type UsersManagerProps = {
  currentUser: Pick<AuthUser, "id" | "role">;
  initialUsers: UserRecord[];
  initialErrorMessage: string | null;
};

type BannerState =
  | {
      tone: "success" | "error";
      message: string;
    }
  | null;

type SortKey = "full_name" | "email" | "role" | "status" | "last_login";
type SortDirection = "asc" | "desc";

type CreateFormState = {
  full_name: string;
  email: string;
  password: string;
  role: Role;
};

type ManageFormState = {
  userId: string;
  full_name: string;
  email: string;
  role: Role;
  status: "active" | "inactive";
  password: string;
};

type ModalState =
  | {
      kind: "create";
    }
  | {
      kind: "manage";
      userId: string;
    }
  | null;

type ApiErrorBody = {
  detail?: string;
  message?: string;
};

const roleRank: Record<Role, number> = {
  super_admin: 0,
  admin: 1,
  user: 2,
};

function formatAccessLabel(role: Role): string {
  if (role === "user") {
    return "Standard";
  }
  if (role === "admin") {
    return "Admin";
  }
  return "Super Admin";
}

function buildCreateForm(role: Role): CreateFormState {
  return {
    full_name: "",
    email: "",
    password: "",
    role,
  };
}

function normalizeText(value: string | null | undefined): string {
  return (value || "").trim().toLowerCase();
}

function canManageTarget(
  actor: Pick<AuthUser, "id" | "role">,
  targetUser: UserRecord,
): boolean {
  if (actor.role === "super_admin") {
    return targetUser.role !== "super_admin" && targetUser.id !== actor.id;
  }
  if (actor.role === "admin") {
    return targetUser.role === "user";
  }
  return false;
}

function canChangeRole(
  actor: Pick<AuthUser, "id" | "role">,
  targetUser: UserRecord,
): boolean {
  return actor.role === "super_admin" && canManageTarget(actor, targetUser);
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as ApiErrorBody;
    return payload.detail || payload.message || "Request failed.";
  } catch {
    return "Request failed.";
  }
}

function ModalFrame({
  children,
  isOpen,
  labelledBy,
  onClose,
}: {
  children: ReactNode;
  isOpen: boolean;
  labelledBy: string;
  onClose: () => void;
}) {
  return (
    <div
      className="modal-backdrop"
      hidden={!isOpen}
      onClick={onClose}
    >
      <div
        className="modal-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        onClick={(event) => event.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

export function UsersManager({
  currentUser,
  initialUsers,
  initialErrorMessage,
}: UsersManagerProps) {
  const router = useRouter();
  const allowedCreateRoles: Role[] =
    currentUser.role === "super_admin" ? ["admin", "user"] : ["user"];

  const [users, setUsers] = useState(initialUsers);
  const [banner, setBanner] = useState<BannerState>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [pageSize, setPageSize] = useState(10);
  const [page, setPage] = useState(1);
  const [sortKey, setSortKey] = useState<SortKey>("full_name");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [modalState, setModalState] = useState<ModalState>(null);
  const [createForm, setCreateForm] = useState<CreateFormState>(
    buildCreateForm(allowedCreateRoles[0]),
  );
  const [manageForm, setManageForm] = useState<ManageFormState | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [manageError, setManageError] = useState<string | null>(null);
  const [isRefreshing, startRefreshing] = useTransition();
  const [isSubmitting, startSubmitting] = useTransition();
  const deferredSearchTerm = useDeferredValue(searchTerm);

  const activeManagedUser =
    modalState?.kind === "manage"
      ? users.find((user) => user.id === modalState.userId) || null
      : null;
  const canManageActiveUser =
    activeManagedUser !== null && canManageTarget(currentUser, activeManagedUser);
  const canChangeActiveUserRole =
    activeManagedUser !== null && canChangeRole(currentUser, activeManagedUser);

  useEffect(() => {
    setUsers(initialUsers);
  }, [initialUsers]);

  useEffect(() => {
    if (modalState === null) {
      document.body.classList.remove("modal-open");
      return;
    }

    document.body.classList.add("modal-open");

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closeModal();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.classList.remove("modal-open");
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [modalState]);

  useEffect(() => {
    setPage(1);
  }, [deferredSearchTerm, pageSize, sortDirection, sortKey]);

  const filteredUsers = users.filter((user) => {
    if (!deferredSearchTerm.trim()) {
      return true;
    }

    const searchValue = deferredSearchTerm.trim().toLowerCase();
    return [
      normalizeText(user.full_name),
      normalizeText(user.email),
      normalizeText(formatAccessLabel(user.role)),
      user.is_active ? "active" : "inactive",
    ].some((value) => value.includes(searchValue));
  });

  const sortedUsers = [...filteredUsers].sort((left, right) => {
    let comparison = 0;

    switch (sortKey) {
      case "email":
        comparison = left.email.localeCompare(right.email);
        break;
      case "role":
        comparison = roleRank[left.role] - roleRank[right.role];
        break;
      case "status":
        comparison = Number(right.is_active) - Number(left.is_active);
        break;
      case "last_login":
        comparison = (right.last_login_at || "").localeCompare(left.last_login_at || "");
        break;
      default: {
        const leftDisplay = left.full_name || left.email;
        const rightDisplay = right.full_name || right.email;
        comparison = leftDisplay.localeCompare(rightDisplay);
      }
    }

    return sortDirection === "asc" ? comparison : -comparison;
  });

  const totalPages = Math.max(1, Math.ceil(sortedUsers.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const pageStartIndex = (safePage - 1) * pageSize;
  const visibleUsers = sortedUsers.slice(pageStartIndex, pageStartIndex + pageSize);

  function closeModal() {
    setModalState(null);
    setCreateError(null);
    setManageError(null);
  }

  function toggleSort(nextSortKey: SortKey) {
    if (sortKey === nextSortKey) {
      setSortDirection((currentValue) => (currentValue === "asc" ? "desc" : "asc"));
      return;
    }

    setSortKey(nextSortKey);
    setSortDirection("asc");
  }

  function openCreateModal() {
    setCreateError(null);
    setBanner(null);
    setCreateForm(buildCreateForm(allowedCreateRoles[0]));
    setModalState({ kind: "create" });
  }

  function openManageModal(user: UserRecord) {
    setManageError(null);
    setBanner(null);
    setManageForm({
      userId: user.id,
      full_name: user.full_name || "",
      email: user.email,
      role: user.role,
      status: user.is_active ? "active" : "inactive",
      password: "",
    });
    setModalState({ kind: "manage", userId: user.id });
  }

  function refreshUsers() {
    setBanner(null);
    startRefreshing(() => {
      router.refresh();
    });
  }

  function updateCreateField(field: keyof CreateFormState, value: string) {
    setCreateForm((currentValue) => ({
      ...currentValue,
      [field]: value,
    }));
  }

  function updateManageField(field: keyof ManageFormState, value: string) {
    setManageForm((currentValue) =>
      currentValue
        ? {
            ...currentValue,
            [field]: value,
          }
        : currentValue,
    );
  }

  function handleCreateSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreateError(null);
    setBanner(null);

    startSubmitting(() => {
      void (async () => {
        const response = await fetch("/api/users", {
          method: "POST",
          headers: {
            accept: "application/json",
            "content-type": "application/json",
          },
          body: JSON.stringify({
            email: createForm.email.trim(),
            full_name: createForm.full_name.trim() || null,
            password: createForm.password,
            role: createForm.role,
          }),
        });

        if (!response.ok) {
          setCreateError(await readErrorMessage(response));
          return;
        }

        const createdUser = (await response.json()) as UserRecord;
        setUsers((currentValue) => [...currentValue, createdUser]);
        setCreateForm(buildCreateForm(allowedCreateRoles[0]));
        setBanner({
          tone: "success",
          message: `${createdUser.email} was created successfully.`,
        });
        closeModal();
      })().catch(() => {
        setCreateError("Unable to create the user right now.");
      });
    });
  }

  function handleManageSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!manageForm || !activeManagedUser) {
      return;
    }

    setManageError(null);
    setBanner(null);

    const payload: Record<string, string | boolean | null> = {};
    const nextFullName = manageForm.full_name.trim() || null;
    if (nextFullName !== (activeManagedUser.full_name || null)) {
      payload.full_name = nextFullName;
    }

    const nextEmail = manageForm.email.trim();
    if (nextEmail !== activeManagedUser.email) {
      payload.email = nextEmail;
    }

    if (
      canChangeActiveUserRole &&
      manageForm.role !== activeManagedUser.role &&
      manageForm.role !== "super_admin"
    ) {
      payload.role = manageForm.role;
    }

    const nextIsActive = manageForm.status === "active";
    if (nextIsActive !== activeManagedUser.is_active) {
      payload.is_active = nextIsActive;
    }

    if (manageForm.password.trim()) {
      payload.password = manageForm.password;
    }

    if (!Object.keys(payload).length) {
      setManageError("No changes to save yet.");
      return;
    }

    startSubmitting(() => {
      void (async () => {
        const response = await fetch(`/api/users/${manageForm.userId}`, {
          method: "PATCH",
          headers: {
            accept: "application/json",
            "content-type": "application/json",
          },
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          setManageError(await readErrorMessage(response));
          return;
        }

        const updatedUser = (await response.json()) as UserRecord;
        setUsers((currentValue) =>
          currentValue.map((user) => (user.id === updatedUser.id ? updatedUser : user)),
        );
        setBanner({
          tone: "success",
          message: `${updatedUser.email} was updated successfully.`,
        });
        closeModal();
      })().catch(() => {
        setManageError("Unable to save those user changes right now.");
      });
    });
  }

  function renderSortIndicator(key: SortKey): string {
    if (sortKey !== key) {
      return "↕";
    }
    return sortDirection === "asc" ? "▲" : "▼";
  }

  const summaryMessage = sortedUsers.length
    ? `Showing ${pageStartIndex + 1} to ${Math.min(pageStartIndex + pageSize, sortedUsers.length)} of ${sortedUsers.length} entries`
    : "No users match your current search.";

  return (
    <>
      <PageHeader
        eyebrow="User Control"
        title="System Users"
        description="Search users, review access, and manage accounts from a single workspace."
        actions={
          <>
            <button
              className="header-action"
              type="button"
              onClick={refreshUsers}
              disabled={isRefreshing}
            >
              {isRefreshing ? "Refreshing..." : "Refresh"}
            </button>
            {!initialErrorMessage ? (
              <button
                className="primary-button primary-button-inline"
                type="button"
                onClick={openCreateModal}
              >
                Create User
              </button>
            ) : null}
          </>
        }
      />

      {banner ? (
        <div className={`banner ${banner.tone === "success" ? "banner-success" : "banner-error"}`}>
          {banner.message}
        </div>
      ) : null}

      {initialErrorMessage ? (
        <div className="banner banner-error">{initialErrorMessage}</div>
      ) : (
        <>
          <section className="panel-card data-table-card">
            <div className="panel-card-header">
              <div>
                <p className="mini-label">User Directory</p>
                <h3>System users</h3>
              </div>
            </div>

            <div className="datatable-controls">
              <label className="datatable-length">
                <select
                  className="field-select"
                  value={pageSize}
                  onChange={(event) => setPageSize(Number(event.target.value))}
                >
                  <option value={10}>10</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                </select>
                <span>entries per page</span>
              </label>

              <label className="datatable-search">
                <span>Search:</span>
                <input
                  type="search"
                  placeholder="Name, email, access, status"
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                />
              </label>
            </div>

            <div className="table-shell">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>
                      <button className={`sort-button${sortKey === "full_name" ? " is-active" : ""}`} type="button" onClick={() => toggleSort("full_name")}>
                        Full Name
                        <span className="sort-indicator">{renderSortIndicator("full_name")}</span>
                      </button>
                    </th>
                    <th>
                      <button className={`sort-button${sortKey === "email" ? " is-active" : ""}`} type="button" onClick={() => toggleSort("email")}>
                        Email
                        <span className="sort-indicator">{renderSortIndicator("email")}</span>
                      </button>
                    </th>
                    <th>
                      <button className={`sort-button${sortKey === "role" ? " is-active" : ""}`} type="button" onClick={() => toggleSort("role")}>
                        Access
                        <span className="sort-indicator">{renderSortIndicator("role")}</span>
                      </button>
                    </th>
                    <th>
                      <button className={`sort-button${sortKey === "status" ? " is-active" : ""}`} type="button" onClick={() => toggleSort("status")}>
                        Status
                        <span className="sort-indicator">{renderSortIndicator("status")}</span>
                      </button>
                    </th>
                    <th>
                      <button className={`sort-button${sortKey === "last_login" ? " is-active" : ""}`} type="button" onClick={() => toggleSort("last_login")}>
                        Last Login
                        <span className="sort-indicator">{renderSortIndicator("last_login")}</span>
                      </button>
                    </th>
                    <th className="actions-column">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleUsers.length ? (
                    visibleUsers.map((user) => {
                      const isManageable = canManageTarget(currentUser, user);
                      return (
                        <tr key={user.id}>
                          <td>
                            <strong>{user.full_name || "No name set"}</strong>
                          </td>
                          <td>{user.email}</td>
                          <td>{formatAccessLabel(user.role)}</td>
                          <td>
                            <span className={`status-pill ${user.is_active ? "status-active" : "status-inactive"}`}>
                              {user.is_active ? "Active" : "Inactive"}
                            </span>
                          </td>
                          <td>{user.last_login_at ? formatDate(user.last_login_at) : "Never"}</td>
                          <td className="actions-column">
                            <button
                              type="button"
                              className={`manage-button${isManageable ? "" : " manage-button-secondary"}`}
                              onClick={() => openManageModal(user)}
                            >
                              Manage
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={6} className="empty-state">
                        No users match your current search.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="datatable-footer">
              <p className="datatable-summary">{summaryMessage}</p>
              <div className="datatable-pagination">
                <button
                  className="page-button"
                  type="button"
                  disabled={safePage <= 1}
                  onClick={() => setPage((currentValue) => Math.max(1, currentValue - 1))}
                >
                  Previous
                </button>
                <span className="page-indicator">
                  Page {safePage} of {totalPages}
                </span>
                <button
                  className="page-button"
                  type="button"
                  disabled={safePage >= totalPages}
                  onClick={() => setPage((currentValue) => Math.min(totalPages, currentValue + 1))}
                >
                  Next
                </button>
              </div>
            </div>
          </section>

          <section className="panel-card support-note-card">
            <div className="panel-card-header">
              <div>
                <p className="mini-label">Permissions</p>
                <h3>Management rules</h3>
              </div>
            </div>

            <div className="info-stack">
              <div className="info-row">
                <span className="info-dot"></span>
                <div>
                  <strong>Admins manage standard users</strong>
                  <p>Admin accounts can create, edit, disable, and reset passwords for standard users only.</p>
                </div>
              </div>
              <div className="info-row">
                <span className="info-dot"></span>
                <div>
                  <strong>Super admins can also manage admins</strong>
                  <p>Admin and standard user roles can be changed here, while super admin accounts stay bootstrap-managed.</p>
                </div>
              </div>
              <div className="info-row">
                <span className="info-dot"></span>
                <div>
                  <strong>Password resets revoke active sessions</strong>
                  <p>Any password reset or deactivation immediately invalidates the target user&apos;s active sessions.</p>
                </div>
              </div>
            </div>
          </section>
        </>
      )}

      <ModalFrame
        isOpen={modalState?.kind === "create"}
        labelledBy="create-user-modal-title"
        onClose={closeModal}
      >
        <div className="modal-header">
          <div>
            <p className="mini-label">Create Account</p>
            <h3 id="create-user-modal-title">Create a new user</h3>
          </div>
          <button type="button" className="modal-close" aria-label="Close" onClick={closeModal}>
            ×
          </button>
        </div>

        <form className="modal-body auth-form" onSubmit={handleCreateSubmit}>
          <label className="field">
            <span>Full name</span>
            <input
              type="text"
              maxLength={255}
              placeholder="Optional display name"
              value={createForm.full_name}
              onChange={(event) => updateCreateField("full_name", event.target.value)}
            />
          </label>

          <label className="field">
            <span>Email</span>
            <input
              type="email"
              maxLength={320}
              required
              value={createForm.email}
              onChange={(event) => updateCreateField("email", event.target.value)}
            />
          </label>

          <label className="field">
            <span>Temporary password</span>
            <input
              type="password"
              minLength={8}
              required
              value={createForm.password}
              onChange={(event) => updateCreateField("password", event.target.value)}
            />
          </label>

          <label className="field">
            <span>Role</span>
            <select
              className="field-select"
              value={createForm.role}
              onChange={(event) => updateCreateField("role", event.target.value as Role)}
            >
              {allowedCreateRoles.map((role) => (
                <option key={role} value={role}>
                  {formatAccessLabel(role)}
                </option>
              ))}
            </select>
          </label>

          {createError ? <p className="error-message">{createError}</p> : null}

          <div className="modal-actions">
            <button type="button" className="header-action" onClick={closeModal}>
              Cancel
            </button>
            <button
              type="submit"
              className={`primary-button primary-button-inline${isSubmitting ? " is-busy" : ""}`}
              disabled={isSubmitting}
            >
              {isSubmitting ? "Creating..." : "Create User"}
            </button>
          </div>
        </form>
      </ModalFrame>

      <ModalFrame
        isOpen={modalState?.kind === "manage" && manageForm !== null}
        labelledBy="manage-user-modal-title"
        onClose={closeModal}
      >
        <div className="modal-header">
          <div>
            <p className="mini-label">Manage User</p>
            <h3 id="manage-user-modal-title">Edit user details</h3>
          </div>
          <button type="button" className="modal-close" aria-label="Close" onClick={closeModal}>
            ×
          </button>
        </div>

        {manageForm ? (
          <form className="modal-body auth-form" onSubmit={handleManageSubmit}>
            <label className="field">
              <span>Full name</span>
              <input
                type="text"
                maxLength={255}
                disabled={!canManageActiveUser}
                value={manageForm.full_name}
                onChange={(event) => updateManageField("full_name", event.target.value)}
              />
            </label>

            <label className="field">
              <span>Email</span>
              <input
                type="email"
                maxLength={320}
                required
                disabled={!canManageActiveUser}
                value={manageForm.email}
                onChange={(event) => updateManageField("email", event.target.value)}
              />
            </label>

            <label className="field">
              <span>Access</span>
              <select
                className="field-select"
                disabled={!canManageActiveUser || !canChangeActiveUserRole}
                value={manageForm.role}
                onChange={(event) => updateManageField("role", event.target.value)}
              >
                {manageForm.role === "super_admin" ? (
                  <option value="super_admin">Super Admin</option>
                ) : (
                  <>
                    <option value="user">Standard</option>
                    <option value="admin">Admin</option>
                  </>
                )}
              </select>
              {!canChangeActiveUserRole && canManageActiveUser ? (
                <small className="field-hint">Only super admins can change access levels.</small>
              ) : null}
            </label>

            <label className="field">
              <span>Status</span>
              <select
                className="field-select"
                disabled={!canManageActiveUser}
                value={manageForm.status}
                onChange={(event) => updateManageField("status", event.target.value)}
              >
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </label>

            <label className="field">
              <span>New temporary password</span>
              <input
                type="password"
                minLength={8}
                placeholder="Leave blank to keep current password"
                disabled={!canManageActiveUser}
                value={manageForm.password}
                onChange={(event) => updateManageField("password", event.target.value)}
              />
            </label>

            {!canManageActiveUser ? (
              <div className="modal-note">
                This account is view-only here and must be managed outside the web UI.
              </div>
            ) : null}

            {manageError ? <p className="error-message">{manageError}</p> : null}

            <div className="modal-actions">
              <button type="button" className="header-action" onClick={closeModal}>
                Cancel
              </button>
              {canManageActiveUser ? (
                <button
                  type="submit"
                  className={`primary-button primary-button-inline${isSubmitting ? " is-busy" : ""}`}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? "Saving..." : "Save Changes"}
                </button>
              ) : null}
            </div>
          </form>
        ) : null}
      </ModalFrame>
    </>
  );
}
