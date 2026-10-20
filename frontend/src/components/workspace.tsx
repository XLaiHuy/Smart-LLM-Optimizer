"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, unwrap, type User } from "@/lib/api";
import { Login } from "./login";
import { ErrorNotice, Spinner } from "./ui";
import { AuthenticatedWorkspace } from "./workspace-shell";

export function Workspace({ dashboard = false }: { dashboard?: boolean }) {
  const client = useQueryClient();
  const [expired, setExpired] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const me = useQuery<User | null>({
    queryKey: ["me"],
    retry: false,
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
      onLogout={() => {
        client.clear();
        client.setQueryData(["me"], null);
        setEpoch((x) => x + 1);
      }}
    />
  );
}
