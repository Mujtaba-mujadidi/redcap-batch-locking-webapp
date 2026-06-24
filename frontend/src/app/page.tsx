import { redirect } from "next/navigation";

import { getSession } from "@/lib/backend";

export default async function HomePage() {
  const session = await getSession();
  redirect(session ? "/app" : "/login");
}
