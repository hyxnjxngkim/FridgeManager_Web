import Link from "next/link";
import { Upload } from "lucide-react";
import { ComingSoon, PageHeader } from "@/components/page-placeholder";
import { Button } from "@/components/ui/button";

export default function InventoryPage() {
  return (
    <>
      <div className="flex items-start justify-between gap-4">
        <PageHeader title="재고" description="냉장고 속 재료와 유통기한을 관리해요." />
        <Button asChild>
          <Link href="/inventory/upload">
            <Upload />
            등록
          </Link>
        </Button>
      </div>
      <ComingSoon
        phase="Phase 1"
        items={["재고 표 (수량, 구입일, 유통기한 D-day 색상)", "직접 추가/수정/삭제", "보관일수 카탈로그로 유통기한 자동 추정"]}
      />
    </>
  );
}
