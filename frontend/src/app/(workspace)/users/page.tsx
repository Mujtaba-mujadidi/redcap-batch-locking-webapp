import { UsersManager } from "@/components/users-manager";
import { BackendRequestError, fetchBackendJson, requireSession } from "@/lib/backend";
import type { UserRecord } from "@/lib/types";

export default async function UsersPage() {
  const session = await requireSession();
  let users: UserRecord[] = [];
  let errorMessage: string | null = null;

  try {
    users = await fetchBackendJson<UserRecord[]>("/api/v1/users");
  } catch (error) {
    if (error instanceof BackendRequestError && error.status === 403) {
      errorMessage = "Your current role can view the workspace but cannot manage users.";
    } else {
      throw error;
    }
  }

  return (
    <UsersManager
      currentUser={{ id: session.user.id, role: session.user.role }}
      initialUsers={users}
      initialErrorMessage={errorMessage}
    />
  );
}
