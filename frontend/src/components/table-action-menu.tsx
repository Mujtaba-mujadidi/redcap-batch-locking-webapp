"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";

type TableActionMenuProps = {
  ariaLabel: string;
  children: ReactNode;
};

export function TableActionMenu({ ariaLabel, children }: TableActionMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const menuId = useId();
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  return (
    <div className="table-action-menu" ref={menuRef}>
      <button
        type="button"
        className="manage-button table-action-trigger"
        aria-label={ariaLabel}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-controls={menuId}
        title="Actions"
        onClick={() => setIsOpen((currentValue) => !currentValue)}
      >
        <span className="table-action-trigger-dots" aria-hidden="true">
          <span></span>
          <span></span>
          <span></span>
        </span>
      </button>
      {isOpen ? (
        <div
          id={menuId}
          className="table-action-menu-list"
          role="menu"
          onClick={() => setIsOpen(false)}
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}
