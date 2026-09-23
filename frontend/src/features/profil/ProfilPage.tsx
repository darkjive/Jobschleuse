import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";

interface AssetUploadProps {
  art: "portrait" | "signature";
  titel: string;
  hinweis: string;
  akzeptiert: string;
}

function AssetUpload({ art, titel, hinweis, akzeptiert }: AssetUploadProps) {
  const dateiname = art === "portrait" ? "portrait.jpg" : "signature.png";
  const [version, setVersion] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const uploadMutation = useMutation({
    mutationFn: (datei: File) => api.profile.assetHochladen(art, datei),
    onSuccess: () => {
      setVersion((v) => v + 1);
      toast.success(`${titel} aktualisiert.`);
    },
    onError: (error) => toast.error(`Upload fehlgeschlagen: ${error.message}`),
  });

  return (
    <Card className="gap-3 p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold">{titel}</h3>
        <Button
          size="sm"
          variant="outline"
          disabled={uploadMutation.isPending}
          onClick={() => inputRef.current?.click()}
        >
          {uploadMutation.isPending ? "lädt hoch…" : "Bild wählen"}
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept={akzeptiert}
          className="hidden"
          onChange={(event) => {
            const datei = event.target.files?.[0];
            if (datei) uploadMutation.mutate(datei);
            event.target.value = "";
          }}
        />
      </div>
      <p className="text-sm text-muted-foreground">{hinweis}</p>
      <div className="flex items-center justify-center rounded-md border border-border bg-muted/30 p-4">
        <img
          key={version}
          src={`/template-assets/assets/${dateiname}?v=${version}`}
          alt={titel}
          className="max-h-40 max-w-full object-contain"
          onError={(event) => {
            event.currentTarget.style.display = "none";
          }}
        />
      </div>
    </Card>
  );
}

export function ProfilPage() {
  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto">
      <h2 className="text-lg font-semibold">Profil</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <AssetUpload
          art="portrait"
          titel="Porträtfoto"
          hinweis="JPG, wird auf dem Deckblatt platziert."
          akzeptiert="image/jpeg"
        />
        <AssetUpload
          art="signature"
          titel="Unterschrift"
          hinweis="PNG mit transparentem Hintergrund, wird im Anschreiben platziert."
          akzeptiert="image/png"
        />
      </div>
    </div>
  );
}
