import { Workspace } from "@/components/workspace";
import { cookies } from "next/headers";
export default async function Page() {
  // A rendering hint only: every private API still authenticates on the backend.
  const initialSignedOut = !(await cookies()).has("smartllm_session");
  return <Workspace initialSignedOut={initialSignedOut} />;
}
