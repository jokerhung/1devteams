"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Loading } from "@/components/ui-app/primitives";
export default function Home() {
  const router = useRouter();
  useEffect(() => {
    const id = localStorage.getItem("lastProjectId");
    if (id)
      apiFetch<Project>(`/projects/${id}`)
        .then(() => router.replace(`/projects/${id}`))
        .catch(() => router.replace("/projects"));
    else router.replace("/projects");
  }, [router]);
  return <Loading />;
}
