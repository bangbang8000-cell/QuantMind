import React from 'react';

interface ComingSoonPageProps {
    title: string;
}

export const ComingSoonPage: React.FC<ComingSoonPageProps> = ({ title }) => (
    <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center space-y-4">
            <div className="w-20 h-20 mx-auto rounded-3xl bg-slate-100 flex items-center justify-center">
                <svg
                    className="w-10 h-10 text-slate-300"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                >
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"
                    />
                </svg>
            </div>
            <h2 className="text-2xl font-black text-slate-800 tracking-tight">
                {title}
            </h2>
            <p className="text-sm text-slate-400 font-medium">
                功能开发中，敬请期待
            </p>
        </div>
    </div>
);
