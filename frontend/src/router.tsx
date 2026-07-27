import {
  createContext,
  type MouseEvent,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

interface RouterValue {
  path: string;
  navigate: (to: string) => void;
}

const RouterContext = createContext<RouterValue | null>(null);

export function RouterProvider({ children }: { children: ReactNode }) {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const update = () => setPath(window.location.pathname);
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);
  const value = useMemo<RouterValue>(
    () => ({
      path,
      navigate: (to) => {
        if (to === window.location.pathname) return;
        window.history.pushState({}, "", to);
        setPath(to);
        window.scrollTo({ top: 0, behavior: "smooth" });
      },
    }),
    [path],
  );
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

export function useRouter(): RouterValue {
  const value = useContext(RouterContext);
  if (!value) throw new Error("useRouter must be used within RouterProvider");
  return value;
}

export function Link({
  to,
  className,
  children,
}: {
  to: string;
  className?: string;
  children: ReactNode;
}) {
  const { navigate } = useRouter();
  const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }
    event.preventDefault();
    navigate(to);
  };
  return (
    <a href={to} className={className} onClick={onClick}>
      {children}
    </a>
  );
}

export function NavLink({
  to,
  end = false,
  className,
  children,
}: {
  to: string;
  end?: boolean;
  className: (state: { isActive: boolean }) => string;
  children: ReactNode;
}) {
  const { path } = useRouter();
  const isActive = end ? path === to : path === to || path.startsWith(`${to}/`);
  return (
    <Link to={to} className={className({ isActive })}>
      {children}
    </Link>
  );
}

