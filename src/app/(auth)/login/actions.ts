"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export type AuthState = { error?: string; message?: string };

function readForm(formData: FormData) {
  return {
    email: String(formData.get("email") ?? "").trim(),
    password: String(formData.get("password") ?? ""),
    next: String(formData.get("next") ?? "/"),
  };
}

function safeNext(next: string) {
  // 외부 주소로 튀지 않도록 내부 경로만 허용
  return next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export async function login(_prev: AuthState, formData: FormData): Promise<AuthState> {
  const { email, password, next } = readForm(formData);
  if (!email || !password) return { error: "이메일과 비밀번호를 입력해 주세요." };

  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) return { error: "로그인에 실패했어요. 이메일과 비밀번호를 확인해 주세요." };

  redirect(safeNext(next));
}

export async function signup(_prev: AuthState, formData: FormData): Promise<AuthState> {
  const { email, password } = readForm(formData);
  if (!email || !password) return { error: "이메일과 비밀번호를 입력해 주세요." };
  if (password.length < 6) return { error: "비밀번호는 6자 이상이어야 해요." };

  const origin = (await headers()).get("origin") ?? "";
  const supabase = await createClient();
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { emailRedirectTo: `${origin}/auth/confirm` },
  });
  if (error) return { error: error.message };

  // 이메일 확인이 꺼져 있으면 바로 세션이 생김
  if (data.session) redirect("/");
  return { message: "확인 메일을 보냈어요. 메일의 링크를 눌러 가입을 완료해 주세요." };
}
