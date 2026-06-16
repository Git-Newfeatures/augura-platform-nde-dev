// icons.jsx — lucide-react adapter for cockpit (mirrors design's window.Icon / <I name="…" />)
import {
  Upload, Brain, Target, Share2, Database, Ruler, FlaskConical, TrendingUp,
  Shield, FileText, Check, CheckCircle2, Lock, Flag, TriangleAlert, Circle,
  ChevronDown, ChevronRight, ArrowLeft, ArrowRight, Dna, User, Eye, Pencil,
  Settings, Activity, GitBranch, LayoutGrid,
} from "lucide-react";

const MAP = {
  upload:       Upload,
  brain:        Brain,
  target:       Target,
  network:      Share2,
  datasets:     Database,
  ruler:        Ruler,
  flask:        FlaskConical,
  statsup:      TrendingUp,
  shield:       Shield,
  page:         FileText,
  check:        Check,
  checkCircle:  CheckCircle2,
  lock:         Lock,
  flag:         Flag,
  alert:        TriangleAlert,
  dot:          Circle,
  chevDown:     ChevronDown,
  chevRight:    ChevronRight,
  arrowLeft:    ArrowLeft,
  arrowRight:   ArrowRight,
  dna:          Dna,
  user:         User,
  eye:          Eye,
  pencil:       Pencil,
  gear:         Settings,
  runs:         Activity,
  lineage:      GitBranch,
  grid:         LayoutGrid,
};

export function Ico({ name, size = 16, color, style }) {
  const Comp = MAP[name];
  if (!Comp) return null;
  return <Comp width={size} height={size} color={color} style={style} />;
}
