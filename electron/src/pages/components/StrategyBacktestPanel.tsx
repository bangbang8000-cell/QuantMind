/**
 * Strategy Lab panel — embedded inside AI-IDE as the "策略回测" log tab.
 * Reuses StrategyLabResultPanel visualization components.
 */
import React, { useMemo, useState, useCallback } from 'react';
import { Card, Empty, Tag, Tabs, Table, Alert, Typography, Button, Space, message } from 'antd';
import type { StrategyLabRunResult, StrategyLabTradeRecord } from '../../features/strategy-lab/types';
import { StrategyLabResultPanel } from '../../features/strategy-lab/components/StrategyLabResultPanel';

interface Props {
  result: StrategyLabRunResult | null;
  loading: boolean;
  code?: string;
  strategyId?: string | null;
  strategyName?: string | null;
}

const StrategyBacktestPanel: React.FC<Props> = ({ result, loading, code, strategyId, strategyName }) => {
  return (
    <div className="flex-1 overflow-auto p-2 bg-white">
      <StrategyLabResultPanel
        result={result}
        loading={loading}
        code={code}
        strategyId={strategyId}
        strategyName={strategyName}
      />
    </div>
  );
};

export default StrategyBacktestPanel;
