import {
  BarChart3,
  CalendarDays,
  ClipboardList,
  Home,
  MessageCircle,
  Refrigerator,
  type LucideIcon,
} from "lucide-react";

export type NavItem = { href: string; label: string; icon: LucideIcon };

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "홈", icon: Home },
  { href: "/inventory", label: "재고", icon: Refrigerator },
  { href: "/calendar", label: "달력", icon: CalendarDays },
  { href: "/chat", label: "채팅", icon: MessageCircle },
  { href: "/plan", label: "식단", icon: ClipboardList },
  { href: "/dashboard", label: "통계", icon: BarChart3 },
];
