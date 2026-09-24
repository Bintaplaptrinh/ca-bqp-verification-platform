/**
 * Drop-in replacements for the lucide-react icons this app used, rendered with
 * Google Fonts "Material Symbols Outlined" instead of inline SVGs. Every export
 * keeps the same name and the same prop shape (size / className / color) lucide
 * used, so call sites do not change - only the `from 'lucide-react'` import path
 * does.
 */

function pxFromClassName(className) {
  if (!className) return null;
  const square = className.match(/(?:^|\s)w-(\d+(?:\.\d+)?)(?:\s|$)/);
  if (square) return Number(square[1]) * 4;
  const arbitrary = className.match(/(?:^|\s)(?:w|text)-\[(\d+(?:\.\d+)?)px\]/);
  if (arbitrary) return Number(arbitrary[1]);
  return null;
}

function createIcon(glyph) {
  function MaterialIcon({ size = undefined, className = "", style = undefined, strokeWidth = undefined, color = undefined, ...rest }) {
    const resolvedSize = size || pxFromClassName(className) || 24;
    return (
      <span
        aria-hidden="true"
        className={`material-symbols-outlined ${className}`.trim()}
        style={{
          fontSize: resolvedSize,
          width: "1em",
          height: "1em",
          lineHeight: 1,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          ...(color ? { color } : {}),
          ...style,
        }}
        {...rest}
      >
        {glyph}
      </span>
    );
  }
  MaterialIcon.displayName = glyph;
  return MaterialIcon;
}

export const ClipboardCheck = createIcon("assignment_turned_in");
export const KeyRound = createIcon("vpn_key");
export const LockKeyhole = createIcon("lock");
export const LogIn = createIcon("login");
export const ShieldCheck = createIcon("verified_user");
export const UserRound = createIcon("account_circle");
export const Loader2 = createIcon("progress_activity");
export const RefreshCw = createIcon("refresh");
export const CheckCircle2 = createIcon("check_circle");
export const XCircle = createIcon("cancel");
export const Plus = createIcon("add");
export const HelpCircle = createIcon("help");
export const UserCheck = createIcon("how_to_reg");
export const UserMinus = createIcon("person_remove");
export const Users = createIcon("group");
export const ChevronDown = createIcon("expand_more");
export const ChevronUp = createIcon("expand_less");
export const ChevronRight = createIcon("chevron_right");
export const Home = createIcon("home");
export const History = createIcon("history");
export const ListChecks = createIcon("checklist");
export const VisibilityOff = createIcon("visibility_off");
export const Check = createIcon("check");
export const Copy = createIcon("content_copy");
export const Lock = createIcon("lock");
export const Mail = createIcon("mail");
export const Trash2 = createIcon("delete");
export const Unlock = createIcon("lock_open");
export const UserPlus = createIcon("person_add");
export const Shield = createIcon("shield");
export const Search = createIcon("search");
export const Clock = createIcon("schedule");
export const User = createIcon("person");
export const Calendar = createIcon("calendar_month");
export const Briefcase = createIcon("work");
export const Building2 = createIcon("apartment");
export const Hash = createIcon("tag");
export const RotateCcw = createIcon("restart_alt");
export const UploadCloud = createIcon("cloud_upload");
export const FileCheck = createIcon("fact_check");
export const FolderOpen = createIcon("folder_open");
export const Scan = createIcon("document_scanner");
export const X = createIcon("close");
export const Database = createIcon("database");
export const Cpu = createIcon("memory");
export const Edit3 = createIcon("edit");
export const ArrowLeft = createIcon("arrow_back");
export const MoreVertical = createIcon("more_vert");
export const Download = createIcon("download");
export const Share2 = createIcon("share");
export const Info = createIcon("info");
export const Award = createIcon("workspace_premium");
export const Server = createIcon("dns");
export const AlertTriangle = createIcon("warning");
export const Eye = createIcon("visibility");
export const ArrowRight = createIcon("arrow_forward");
export const CreditCard = createIcon("credit_card");
export const FileText = createIcon("description");
export const AlertCircle = createIcon("error");
export const Settings = createIcon("settings");
export const LogOut = createIcon("logout");
export const ExternalLink = createIcon("open_in_new");
export const Layers = createIcon("layers");
export const Image = createIcon("image");
export const FileImage = createIcon("photo");
export const Filter = createIcon("filter_list");
