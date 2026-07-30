import { mediaUrl } from "@/lib/api";

const COLORS = ["#FF0055", "#00F0FF", "#7C3AED", "#F59E0B", "#10B981", "#EC4899"];

function initials(name = "") {
  return name
    .trim()
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

export function AvatarCircle({ name, picture, size = 40, className = "", ring = true, testid }) {
  const dim = { width: size, height: size };
  const color = COLORS[(name?.charCodeAt(0) || 0) % COLORS.length];
  const ringCls = ring ? "border-2 border-[#0A0A0C]" : "";
  if (picture) {
    return (
      <img
        data-testid={testid}
        src={mediaUrl(picture)}
        alt={name}
        style={dim}
        className={`rounded-full object-cover ${ringCls} ${className}`}
      />
    );
  }
  return (
    <div
      data-testid={testid}
      style={{ ...dim, backgroundColor: color }}
      className={`rounded-full flex items-center justify-center font-bold text-white ${ringCls} ${className}`}
    >
      <span style={{ fontSize: size * 0.4 }}>{initials(name) || "?"}</span>
    </div>
  );
}
