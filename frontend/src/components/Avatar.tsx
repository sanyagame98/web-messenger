import { assetUrl } from "@/lib/api";

interface AvatarProps {
  name: string;
  url?: string | null;
  size?: number;
  online?: boolean;
}

function colorFor(name: string): string {
  const palette = [
    "bg-rose-500",
    "bg-orange-500",
    "bg-amber-500",
    "bg-emerald-500",
    "bg-teal-500",
    "bg-sky-500",
    "bg-indigo-500",
    "bg-fuchsia-500",
    "bg-pink-500",
  ];
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return palette[h % palette.length];
}

export function Avatar({ name, url, size = 40, online }: AvatarProps) {
  const initial = (name?.trim()?.[0] || "?").toUpperCase();
  const src = assetUrl(url);
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={name}
          width={size}
          height={size}
          className="rounded-full object-cover"
          style={{ width: size, height: size }}
        />
      ) : (
        <div
          className={`flex items-center justify-center rounded-full font-semibold text-white ${colorFor(
            name,
          )}`}
          style={{ width: size, height: size, fontSize: size * 0.45 }}
        >
          {initial}
        </div>
      )}
      {online !== undefined && (
        <span
          className={`absolute bottom-0 right-0 block rounded-full ring-2 ring-white dark:ring-slate-900 ${
            online ? "bg-emerald-500" : "bg-slate-400"
          }`}
          style={{ width: size * 0.28, height: size * 0.28 }}
        />
      )}
    </div>
  );
}
