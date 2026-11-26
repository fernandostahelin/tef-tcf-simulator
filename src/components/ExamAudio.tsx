"use client";

import { useEffect, useState } from "react";

async function isMissingAudio(src: string): Promise<boolean> {
  try {
    const response = await fetch(src, { method: "HEAD" });
    return response.status === 404;
  } catch {
    return false;
  }
}

export function ExamAudio({ src, className }: { src: string; className?: string }) {
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setMissing(false);
    isMissingAudio(src).then((missingFile) => {
      if (!cancelled && missingFile) setMissing(true);
    });
    return () => {
      cancelled = true;
    };
  }, [src]);

  return (
    <div className="space-y-2">
      <audio
        controls
        src={src}
        className={className}
        onError={() => {
          void isMissingAudio(src).then((missingFile) => {
            if (missingFile) setMissing(true);
          });
        }}
      >
        Votre navigateur ne prend pas en charge la lecture audio.
      </audio>
      {missing && (
        <p
          role="alert"
          className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
        >
          Cet enregistrement est introuvable (erreur 404). Les fichiers audio se génèrent sur
          votre machine et ne sont pas inclus dans le projet. Exécutez{" "}
          <code className="rounded bg-amber-100 px-1 py-0.5 font-mono text-[0.8em]">
            npm run generate:audio
          </code>
          {", puis rechargez la page."}
        </p>
      )}
    </div>
  );
}
