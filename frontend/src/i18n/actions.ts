"use server";
import { cookies } from "next/headers";

export async function setLocale(value: "vi" | "en") {
  (await cookies()).set("NEXT_LOCALE", value, {
    path: "/",
    maxAge: 31536000,
    sameSite: "lax",
  });
}
