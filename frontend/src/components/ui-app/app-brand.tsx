import Image from "next/image";

export function AppBrand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex min-w-0 items-center gap-2.5" aria-label="1Teams">
      <Image
        src="/brand/aiteams-icon.png"
        alt=""
        width={40}
        height={40}
        aria-hidden="true"
        className="size-10 shrink-0 object-contain"
      />
      {!compact && (
        <span
          aria-hidden="true"
          className="text-[26px] leading-none font-normal tracking-tight text-stone-900"
        >
          <span className="text-[#21c7cc]">1</span>Teams
        </span>
      )}
    </span>
  );
}
