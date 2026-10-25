import { toast as sonner } from "sonner";

// sonner liefert Stapel und Animation, das Aussehen kommt von .ds-toast (siehe components/ui/sonner.tsx).
// Töne wie in den anderen Apps: success/error spielen über das Designsystem (/ds/sounds.js), wenn eingeschaltet.
export const toast = {
  success: (text: string) => {
    window.dsSound?.play("success");
    return sonner.success(text);
  },
  error: (text: string) => {
    window.dsSound?.play("error");
    return sonner.error(text, { duration: Infinity });
  },
};
