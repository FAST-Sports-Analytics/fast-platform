"use client";

import Image from "next/image";
import { useEffect, useState } from "react";

type ProductScreenshotProps = {
  src: string;
  alt: string;
  label: string;
  caption?: string;
  priority?: boolean;
  className?: string;
};

export function ProductScreenshot({ src, alt, label, caption, priority = false, className = "" }: ProductScreenshotProps) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.body.classList.add("screenshot-modal-open");
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.classList.remove("screenshot-modal-open");
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return <>
    <figure className={`product-screenshot ${className}`.trim()}>
      <button type="button" className="screenshot-button" onClick={() => setOpen(true)} aria-label={`Enlarge ${label}`}>
        <span className="screenshot-frame-bar"><i/><i/><i/><small>{label}</small><b>↗</b></span>
        <span className="screenshot-image-wrap">
          <Image src={src} alt={alt} fill sizes="(max-width: 900px) 100vw, 70vw" priority={priority}/>
        </span>
      </button>
      {caption && <figcaption>{caption}</figcaption>}
    </figure>
    {open && <div className="screenshot-modal" role="dialog" aria-modal="true" aria-label={label} onClick={() => setOpen(false)}>
      <button type="button" className="screenshot-modal-close" onClick={() => setOpen(false)} aria-label="Close enlarged screenshot">Close ×</button>
      <div className="screenshot-modal-image" onClick={(event) => event.stopPropagation()}>
        <Image src={src} alt={alt} fill sizes="96vw" priority/>
      </div>
    </div>}
  </>;
}
