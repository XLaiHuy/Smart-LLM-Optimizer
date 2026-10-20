import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";

export default getRequestConfig(async () => {
  const preferred = (await cookies()).get("NEXT_LOCALE")?.value;
  const locale = preferred === "en" ? "en" : "vi";
  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  };
});
