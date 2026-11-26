import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
      {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
    </div>
  );
}

export function ComingSoon({ phase, items }: { phase: string; items: string[] }) {
  return (
    <Card className="border-dashed">
      <CardHeader>
        <CardTitle className="text-base">{phase}에서 만들 기능</CardTitle>
        <CardDescription>지금은 빈 화면이에요.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
