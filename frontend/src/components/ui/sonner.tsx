import { Toaster as Sonner, type ToasterProps } from "sonner"
import { X } from "lucide-react"

// sonner übernimmt Stapel, Position und Animation; Optik und Farben kommen von .ds-toast (Harmonia).
const Toaster = ({ ...props }: ToasterProps) => (
  <Sonner
    position="bottom-center"
    closeButton
    icons={{ close: <X className="size-4" /> }}
    toastOptions={{
      unstyled: true,
      classNames: {
        toast: "ds-toast",
        title: "ds-toast-text",
        error: "error",
        warning: "warn",
        info: "info",
        closeButton: "ds-toast-close ds-btn ghost sm icon",
      },
    }}
    {...props}
  />
)

export { Toaster }
