"use client";

import React, { useRef, useState, useEffect } from "react";
import { motion } from "framer-motion";
import { useLocation, useNavigate } from "react-router-dom";
import { LayoutDashboard, Box, Truck, Wallet, LineChart } from "lucide-react";
import { cn } from "../../lib/utils";

const NAV_ITEMS = [
  { label: "Dashboard", path: "/", icon: LayoutDashboard },
  { label: "Map", path: "/map", icon: Box },
  { label: "Shipments", path: "/shipments", icon: Truck },
  { label: "Recovery", path: "/recovery", icon: Wallet },
  { label: "Analytics", path: "/analytics", icon: LineChart },
];

export const SlideTabs = () => {
  const location = useLocation();
  const navigate = useNavigate();

  // Find the index of the currently active route, default to 0 (Dashboard)
  const activeIndex = Math.max(
    0,
    NAV_ITEMS.findIndex((item) => item.path === location.pathname)
  );

  const [position, setPosition] = useState({
    left: 0,
    width: 0,
    opacity: 0,
  });
  
  const tabsRef = useRef<(HTMLLIElement | null)[]>([]);

  // Update cursor position when the active route changes (or on mount)
  useEffect(() => {
    const activeTab = tabsRef.current[activeIndex];
    if (activeTab) {
      const { width } = activeTab.getBoundingClientRect();
      setPosition({
        left: activeTab.offsetLeft,
        width,
        opacity: 1,
      });
    }
  }, [activeIndex, location.pathname]);

  return (
    <ul
      onMouseLeave={() => {
        // When the mouse leaves the container, reset the cursor
        // to the position of the currently active route tab.
        const activeTab = tabsRef.current[activeIndex];
        if (activeTab) {
          const { width } = activeTab.getBoundingClientRect();
          setPosition({
            left: activeTab.offsetLeft,
            width,
            opacity: 1,
          });
        }
      }}
      className="relative mx-auto flex w-fit rounded-full bg-white p-1 shadow-sm"
      style={{
        border: '1px solid rgba(0,0,0,0.05)',
        boxShadow: '0 2px 10px rgba(0,0,0,0.03)',
      }}
    >
      {NAV_ITEMS.map((item, i) => (
        <Tab
          key={item.label}
          path={item.path}
          ref={(el) => { tabsRef.current[i] = el; }}
          setPosition={setPosition}
        >
          <div className="flex items-center gap-2">
            <item.icon size={16} />
            {item.label}
          </div>
        </Tab>
      ))}

      <Cursor position={position} />
    </ul>
  );
};

import { Link } from "react-router-dom";

// The Tab component is wrapped in forwardRef to accept a ref from its parent.
const Tab = React.forwardRef<
  HTMLLIElement,
  { children: React.ReactNode; setPosition: any; path: string }
>(({ children, setPosition, path }, ref) => {
  return (
    <li
      ref={ref}
      onMouseEnter={(e) => {
        const el = e.currentTarget;
        if (!el) return;

        const { width } = el.getBoundingClientRect();

        setPosition({
          left: el.offsetLeft,
          width,
          opacity: 1,
        });
      }}
      className="relative z-10 block cursor-pointer text-[13px] font-medium text-white mix-blend-difference transition-colors"
    >
      <Link to={path} className="px-3 py-2 md:px-5 md:py-2.5 flex w-full h-full" onClick={(e) => e.stopPropagation()}>
        {children}
      </Link>
    </li>
  );
});

const Cursor = ({ position }: { position: any }) => {
  return (
    <motion.li
      animate={{
        ...position,
      }}
      transition={{ type: "spring", stiffness: 400, damping: 30 }}
      className="absolute z-0 h-[36px] rounded-full bg-[#18181A] md:h-[40px]"
      style={{ top: '4px' }}
    />
  );
};
