"use client";

import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

type TableActionMenuProps = {
  ariaLabel: string;
  children: ReactNode;
};

const MENU_MIN_WIDTH_PX = 192;

export function TableActionMenu({ ariaLabel, children }: TableActionMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});
  const menuId = useId();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  const updateMenuPosition = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) {
      return;
    }

    const rect = trigger.getBoundingClientRect();
    const viewportPadding = 8;
    const left = Math.min(
      Math.max(viewportPadding, rect.right - MENU_MIN_WIDTH_PX),
      window.innerWidth - MENU_MIN_WIDTH_PX - viewportPadding,
    );

    setMenuStyle({
      position: "fixed",
      top: rect.bottom + 4,
      left,
      minWidth: MENU_MIN_WIDTH_PX,
      zIndex: 200,
    });
  }, []);

  useLayoutEffect(() => {
    if (!isOpen) {
      return;
    }

    updateMenuPosition();

    window.addEventListener("resize", updateMenuPosition);
    window.addEventListener("scroll", updateMenuPosition, true);

    return () => {
      window.removeEventListener("resize", updateMenuPosition);
      window.removeEventListener("scroll", updateMenuPosition, true);
    };
  }, [isOpen, updateMenuPosition]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (containerRef.current?.contains(target) || menuRef.current?.contains(target)) {
        return;
      }
      setIsOpen(false);
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

  const menuList =
    isOpen && typeof document !== "undefined"
      ? createPortal(
          <div
            id={menuId}
            ref={menuRef}
            className="table-action-menu-list table-action-menu-list-portal"
            role="menu"
            style={menuStyle}
            onClick={(event) => {
              if ((event.target as HTMLElement).closest("a.table-action-menu-link")) {
                setIsOpen(false);
              }
            }}
          >
            {children}
          </div>,
          document.body,
        )
      : null;

  return (
    <div className="table-action-menu" ref={containerRef}>
      <button
        ref={triggerRef}
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
      {menuList}
    </div>
  );
}
