import { redirect } from "next/navigation";

import { getSession } from "@/lib/backend";
import { isDesktopMode } from "@/lib/env";

export default async function HomePage() {
  if (isDesktopMode) {
    redirect("/jobs");
  }

  const session = await getSession();
  redirect(session ? "/app" : "/login");
}
