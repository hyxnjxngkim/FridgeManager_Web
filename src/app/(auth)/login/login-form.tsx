"use client";

import { useActionState, useState } from "react";
import { Refrigerator } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { login, signup, type AuthState } from "./actions";

export function LoginForm({ next }: { next: string }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [state, action, pending] = useActionState<AuthState, FormData>(
    mode === "login" ? login : signup,
    {},
  );

  return (
    <Card className="w-full max-w-sm">
      <CardHeader className="items-center text-center">
        <div className="mb-2 flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
          <Refrigerator className="size-6" />
        </div>
        <CardTitle className="text-xl">냉장고를 부탁해</CardTitle>
        <CardDescription>버릴 뻔한 재료부터 맛있게 구출해요</CardDescription>
      </CardHeader>
      <CardContent>
        <form action={action} className="flex flex-col gap-4">
          <input type="hidden" name="next" value={next} />
          <div className="flex flex-col gap-2">
            <Label htmlFor="email">이메일</Label>
            <Input id="email" name="email" type="email" autoComplete="email" required />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="password">비밀번호</Label>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={6}
              required
            />
          </div>

          {state.error && <p className="text-sm text-destructive">{state.error}</p>}
          {state.message && <p className="text-sm text-primary">{state.message}</p>}

          <Button type="submit" disabled={pending}>
            {pending ? "처리 중…" : mode === "login" ? "로그인" : "회원가입"}
          </Button>
        </form>

        <p className="mt-4 text-center text-sm text-muted-foreground">
          {mode === "login" ? "처음이신가요?" : "이미 계정이 있나요?"}{" "}
          <button
            type="button"
            className="font-medium text-primary underline-offset-4 hover:underline"
            onClick={() => setMode(mode === "login" ? "signup" : "login")}
          >
            {mode === "login" ? "회원가입" : "로그인"}
          </button>
        </p>
      </CardContent>
    </Card>
  );
}
