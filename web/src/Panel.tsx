import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
export function Panel({ children, label, onClose }: {
    children: ReactNode;
    label: string;
    onClose: () => void;
}) {
    const dialog = useRef<HTMLDialogElement>(null);
    useEffect(() => {
        const previous = document.activeElement;
        dialog.current?.showModal();
        const oldOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        return () => { document.body.style.overflow = oldOverflow; if (previous instanceof HTMLElement)
            previous.focus(); };
    }, []);
    return <dialog ref={dialog} className="panel-dialog" aria-label={label} onCancel={event => { event.preventDefault(); onClose(); }}>{children}</dialog>;
}
