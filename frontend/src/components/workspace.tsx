"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, unwrap, type User } from "@/lib/api";
import { Login } from "./login";
import { ErrorNotice, Spinner } from "./ui";
import dynamic from "next/dynamic";
const AuthenticatedWorkspace = dynamic(
  () => import("./workspace-shell").then((m) => m.AuthenticatedWorkspace),
  {
    loading: () => (
      <main className="app-loading" role="status">
        <Spinner />
      </main>
    ),
  },
);

export function Workspace({
  dashboard = false,
  settings = false,
  pipeline = false,
  initialSignedOut = false,
}: {
  dashboard?: boolean;
  settings?: boolean;
  pipeline?: boolean;
  initialSignedOut?: boolean;
}) {
  const client = useQueryClient();
  const [expired, setExpired] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const me = useQuery<User | null>({
    queryKey: ["me"],
    initialData: initialSignedOut ? null : undefined,
    initialDataUpdatedAt: 0,
    retry: (failureCount, error) => {
      const status =
        (error as { status?: number; response?: { status?: number } })
          ?.status ??
        (error as { status?: number; response?: { status?: number } })?.response
          ?.status;
      if (status === 401) return false;
      return failureCount < 3;
    },
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 3000),
    queryFn: async () => {
      const response = await api.GET("/v1/auth/me");
      return response.response.status === 401 ? null : unwrap(response);
    },
  });
  useEffect(() => {
    const expire = () => {
      void client.cancelQueries().then(() => {
        client.clear();
        client.setQueryData(["me"], null);
        setExpired(true);
        setEpoch((x) => x + 1);
      });
    };
    window.addEventListener("auth-expired", expire);
    return () => window.removeEventListener("auth-expired", expire);
  }, [client]);
  if (me.isLoading)
    return (
      <main className="app-loading" role="status">
        <Spinner />
      </main>
    );
  if (me.isError)
    return (
      <main className="fatal">
        <ErrorNotice error={me.error} />
        <button className="button" onClick={() => me.refetch()}>
          Thử lại / Try again
        </button>
      </main>
    );
  if (!me.data)
    return (
      <Login
        key={expired ? "expired" : "signed-out"}
        expired={expired}
        onSuccess={(user) => {
          setExpired(false);
          client.setQueryData(["me"], user);
        }}
      />
    );
  return (
    <AuthenticatedWorkspace
      key={`${me.data.id}-${epoch}`}
      user={me.data}
      dashboard={dashboard}
      settings={settings}
      pipeline={pipeline}
      onLogout={() => {
        client.clear();
        client.setQueryData(["me"], null);
        setEpoch((x) => x + 1);
      }}
    />
  );
}
