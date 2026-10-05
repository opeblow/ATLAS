"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { completeSignIn } from "../../lib/auth";

export default function AuthCallbackPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const url = new URL(window.location.href);
    if (!url.searchParams.has("code") && !url.searchParams.has("error")) {
      router.replace("/");
      return () => {
        active = false;
      };
    }
    completeSignIn()
      .then(() => {
        if (active) router.replace("/dashboard");
      })
      .catch((cause: Error) => {
        if (active) setError(cause.message);
      });
    return () => {
      active = false;
    };
  }, [router]);

  return (
    <main className="auth-gate">
      <section className="auth-card">
        <h1>{error ? "Sign-in failed" : "Finishing sign-in"}</h1>
        <p role={error ? "alert" : "status"}>
          {error || "Verifying your secure Cognito session…"}
        </p>
        {error && <a href="/">Return to ATLAS</a>}
      </section>
    </main>
  );
}
