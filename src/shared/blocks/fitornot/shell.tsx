import type { ReactNode } from 'react';

type FitOrNotShellProps = {
  children: ReactNode;
};

export function FitOrNotShell({ children }: FitOrNotShellProps) {
  return (
    <div className="min-h-screen bg-[#F4F7F9] text-slate-700">
      <div className="mx-auto flex min-h-screen w-full max-w-[1440px] flex-col">
        {children}
      </div>
    </div>
  );
}
