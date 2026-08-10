import React from 'react';
import {
  ArrowLeftRight,
  Boxes,
  Layers,
  CircleUserRound,
  FlaskConical,
  FlaskRound,
  LayoutDashboard,
  LineChart,
  Orbit,
  Rss,
  Search,
  ShieldCheck,
  SquareTerminal,
  TestTube2,
  Brain,
  BarChart3
} from 'lucide-react';
import { motion } from 'framer-motion';
import { useSelector } from 'react-redux';
import { selectCurrentMarket } from '../../store/slices/uiSlice';
import { getMarketConfig } from '../../config/marketConfig';

interface FloatingNavBarProps {
  current?: string;
  onChange?: (section: string) => void;
}

interface NavItemConfig {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

export const FloatingNavBar: React.FC<FloatingNavBarProps> = ({ current, onChange }) => {
  const user = useSelector((state: any) => state.auth.user);
  const isAdmin = user?.is_admin || false;
  const currentMarket = useSelector(selectCurrentMarket);
  const marketLabel = getMarketConfig(currentMarket).label;

  const navItems: NavItemConfig[] = [
    { id: 'dashboard', label: marketLabel, icon: LayoutDashboard },
    { id: 'market-analysis', label: '市场分析', icon: BarChart3 },
    { id: 'strategy', label: '智能策略', icon: LineChart },
    { id: 'ai-ide', label: 'AI-IDE', icon: SquareTerminal },
    { id: 'backtest', label: '回测中心', icon: FlaskConical },
    { id: 'agent', label: 'QuantBot', icon: Orbit },
    { id: 'model-training', label: '模型训练', icon: Layers },
    { id: 'model-registry', label: '模型管理', icon: Boxes },
    { id: 'research', label: '投研平台', icon: Search },
    { id: 'trading', label: '模拟交易', icon: ArrowLeftRight },
    { id: 'rss-news', label: 'RSS信息流', icon: Rss },
    { id: 'alpha-research', label: 'Alpha研究', icon: TestTube2 },
    { id: 'trading-agents', label: '投研分析', icon: Brain },
    { id: 'profile', label: '个人中心', icon: CircleUserRound }
  ];

  if (isAdmin) {
    navItems.push({ id: 'admin', label: '后台管理', icon: ShieldCheck });
  }

  const groupedNavItems: NavItemConfig[][] = [
    navItems.filter((item) => ['dashboard', 'market-analysis', 'strategy', 'ai-ide', 'backtest', 'agent'].includes(item.id)),
    navItems.filter((item) => ['model-training', 'model-registry', 'research', 'trading', 'rss-news', 'alpha-research', 'trading-agents'].includes(item.id)),
    navItems.filter((item) => ['profile', 'admin'].includes(item.id))
  ].filter((group) => group.length > 0);

  return (
    <nav className="bottom-dock" aria-label="主导航">
      <div className="bottom-dock-inner">
        {groupedNavItems.map((group, groupIndex) => (
          <React.Fragment key={`group-${groupIndex}`}>
            <div className="dock-group">
              {group.map((item) => {
                const Icon = item.icon;
                const isActive = current === item.id;

                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => onChange?.(item.id)}
                    className={`dock-item ${isActive ? 'active' : ''}`}
                    aria-current={isActive ? 'page' : undefined}
                    title={item.label}
                  >
                    {isActive && (
                      <motion.span
                        layoutId="dock-active-indicator"
                        className="dock-active-indicator"
                        transition={{ type: 'spring', bounce: 0.15, duration: 0.32 }}
                        aria-hidden="true"
                      />
                    )}
                    <Icon className="dock-icon" />
                    <span className="dock-label">{item.label}</span>
                  </button>
                );
              })}
            </div>
            {groupIndex < groupedNavItems.length - 1 && (
              <span className="dock-divider" aria-hidden="true" />
            )}
          </React.Fragment>
        ))}
      </div>
    </nav>
  );
};
