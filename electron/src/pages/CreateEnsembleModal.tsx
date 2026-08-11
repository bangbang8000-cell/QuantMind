import React, { useMemo, useState } from 'react';
import { Button, Input, Radio, Modal, Select, Slider, message, Tag, Tooltip } from 'antd';
import { clsx } from 'clsx';
import { Layers, Info, TrendingUp } from 'lucide-react';
import { UserModelRecord, modelTrainingService } from '../services/modelTrainingService';
import { getMeta, getMetrics, extractModelTypeShort, modelDisplayName } from './modelRegistryUtils';

interface CreateEnsembleModalProps {
  open: boolean;
  onCancel: () => void;
  onCreated: (modelId: string) => void;
  models: UserModelRecord[];
}

type WeightStrategy = 'equal' | 'icir' | 'manual';

function extractIcirs(models: UserModelRecord[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const m of models) {
    const metrics = getMetrics(m);
    const icir =
      Number(metrics.val_rank_icir ?? metrics.val_icir ?? 0) ||
      Number((getMeta(m).metrics as any)?.val_rank_icir ?? 0);
    out[m.model_id] = Number.isFinite(icir) ? icir : 0;
  }
  return out;
}

export const CreateEnsembleModal: React.FC<CreateEnsembleModalProps> = ({
  open,
  onCancel,
  onCreated,
  models,
}) => {
  const [strategy, setStrategy] = useState<WeightStrategy>('equal');
  const [displayName, setDisplayName] = useState('');
  const [manualWeights, setManualWeights] = useState<Record<string, number>>({});
  const [creating, setCreating] = useState(false);
  const [fusionStrategy, setFusionStrategy] = useState<'linear' | 'majority_vote' | 'periodic_hierarchy' | 'confidence_gate'>('linear');
  const [periodicBoundary, setPeriodicBoundary] = useState(10);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.6);

  const icirs = useMemo(() => extractIcirs(models), [models]);

  // Default display name: algo + horizon summary
  const defaultName = useMemo(() => {
    const parts = models.map((m) => {
      const algo = extractModelTypeShort(m);
      const h = Number(getMeta(m).target_horizon_days ?? getMeta(m).horizon_days ?? 0);
      return h > 0 ? `${algo || 'M'}T${h}` : algo || 'M';
    });
    return parts.length ? `Ensemble_${parts.join('+')}` : 'Ensemble';
  }, [models]);

  // Computed weights based on strategy
  const computedWeights = useMemo(() => {
    const n = models.length;
    if (n === 0) return {};
    if (strategy === 'equal') {
      return Object.fromEntries(models.map((m) => [m.model_id, 1 / n]));
    }
    if (strategy === 'icir') {
      const vals = models.map((m) => Math.max(icirs[m.model_id] ?? 0, 0));
      const total = vals.reduce((a, b) => a + b, 0);
      if (total <= 0) return Object.fromEntries(models.map((m) => [m.model_id, 1 / n]));
      return Object.fromEntries(models.map((m, i) => [m.model_id, vals[i] / total]));
    }
    // manual
    const vals = models.map((m) => Math.max(manualWeights[m.model_id] ?? 0, 0));
    const total = vals.reduce((a, b) => a + b, 0) || 1;
    return Object.fromEntries(models.map((m, i) => [m.model_id, vals[i] / total]));
  }, [models, strategy, manualWeights, icirs]);

  const totalWeight = Object.values(computedWeights).reduce((a, b) => a + b, 0);

  const handleCreate = async () => {
    if (models.length < 2) {
      message.warning('请至少选择 2 个模型');
      return;
    }
    if (strategy === 'manual') {
      const invalid = models.some((m) => !(manualWeights[m.model_id] > 0));
      if (invalid) {
        message.warning('manual 策略下每个模型权重必须大于 0');
        return;
      }
    }
    setCreating(true);
    try {
      const created = await modelTrainingService.createEnsemble({
        source_model_ids: models.map((m) => m.model_id),
        display_name: displayName.trim() || defaultName,
        weight_strategy: strategy,
        manual_weights: strategy === 'manual' ? { ...manualWeights } : undefined,
        fusion_strategy: fusionStrategy,
        strategy_config: fusionStrategy === 'periodic_hierarchy'
          ? { periodic_boundary: periodicBoundary }
          : fusionStrategy === 'confidence_gate'
            ? { confidence_threshold: confidenceThreshold }
            : undefined,
      });
      message.success(`融合模型已创建: ${created.model_id}`);
      onCreated(created.model_id);
      onCancel();
    } catch (err: any) {
      message.error(`创建融合模型失败: ${err?.response?.data?.detail ?? err?.message ?? '未知错误'}`);
    } finally {
      setCreating(false);
    }
  };

  return (
    <Modal
      title={
        <span className="flex items-center gap-2 font-bold">
          <Layers size={15} className="text-blue-600" />
          创建多模型融合
          <Tag color="blue" className="ml-1 font-mono">{models.length} 个源模型</Tag>
        </span>
      }
      open={open}
      onCancel={onCancel}
      width={560}
      footer={
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-slate-400">
            权重合计: <b className="text-blue-600">{totalWeight.toFixed(3)}</b>
          </span>
          <div className="flex gap-2">
            <Button onClick={onCancel}>取消</Button>
            <Button type="primary" loading={creating} onClick={handleCreate} className="bg-blue-600">
              创建融合模型
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-4 py-1">
        {/* 源模型摘要 */}
        <div className="space-y-1.5 max-h-44 overflow-y-auto custom-scrollbar pr-1">
          {models.map((m) => (
            <div key={m.model_id} className="flex items-center justify-between bg-slate-50 rounded-lg px-3 py-2">
              <div className="min-w-0">
                <div className="text-[11px] font-bold text-slate-700 truncate">{modelDisplayName(m)}</div>
                <div className="text-[9px] text-slate-400 font-mono">{m.model_id}</div>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <span className="text-[9px] text-slate-500 font-mono bg-white px-1.5 py-0.5 rounded border border-slate-200">
                  {extractModelTypeShort(m) || getMeta(m).model_type}
                </span>
                {Number(getMeta(m).target_horizon_days) > 0 && (
                  <span className="text-[9px] text-slate-500 font-mono bg-white px-1.5 py-0.5 rounded border border-slate-200">
                    T{getMeta(m).target_horizon_days}
                  </span>
                )}
                {strategy !== 'manual' && (
                  <span className="text-[9px] font-mono text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded">
                    {((computedWeights[m.model_id] ?? 0) * 100).toFixed(0)}%
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* 融合名称 */}
        <div>
          <div className="text-[10px] font-black text-slate-500 mb-1">融合模型名称</div>
          <Input
            size="small"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder={defaultName}
            className="rounded-lg"
          />
        </div>

        {/* 权重策略 */}
        <div>
          <div className="text-[10px] font-black text-slate-500 mb-1.5">权重策略</div>
          <Radio.Group value={strategy} onChange={(e) => setStrategy(e.target.value)} className="w-full">
            <div className="grid grid-cols-3 gap-2">
              <Radio.Button value="equal" className="text-center">
                <Tooltip title="每个模型等权 1/N">
                  <span className="text-[11px] font-bold">等权</span>
                </Tooltip>
              </Radio.Button>
              <Radio.Button value="icir" className="text-center">
                <Tooltip title="按 Val Rank ICIR 归一化加权，ICIR 高的模型权重更大">
                  <span className="text-[11px] font-bold flex items-center justify-center gap-1">
                    ICIR 加权 <TrendingUp size={10} />
                  </span>
                </Tooltip>
              </Radio.Button>
              <Radio.Button value="manual" className="text-center">
                <Tooltip title="手动拖动滑块设定权重">
                  <span className="text-[11px] font-bold">手动</span>
                </Tooltip>
              </Radio.Button>
            </div>
          </Radio.Group>
        </div>

        {/* 融合算法 */}
        <div>
          <div className="text-[10px] font-black text-slate-500 mb-1.5">融合算法</div>
          <Select
            size="small"
            value={fusionStrategy}
            onChange={setFusionStrategy}
            className="w-full"
            options={[
              { value: 'linear', label: '线性加权 — 加权平均（默认）' },
              { value: 'majority_vote', label: '投票裁决 — 方向一致才保留，不一致降权' },
              { value: 'periodic_hierarchy', label: '周期分层 — 长周期定方向，短周期定时' },
              { value: 'confidence_gate', label: '置信度门控 — 共识不足按阈值降权/丢弃' },
            ]}
          />
          {fusionStrategy === 'periodic_hierarchy' && (
            <div className="mt-2">
              <div className="flex justify-between text-[9px] text-slate-400 mb-0.5">
                <span>短/长周期分界线（≥此天数为长周期）</span>
                <span className="font-mono font-bold text-blue-600">{periodicBoundary} 天</span>
              </div>
              <Slider
                min={1}
                max={30}
                value={periodicBoundary}
                onChange={setPeriodicBoundary}
              />
            </div>
          )}
          {fusionStrategy === 'confidence_gate' && (
            <div className="mt-2">
              <div className="flex justify-between text-[9px] text-slate-400 mb-0.5">
                <span>共识阈值（方向一致模型占比）</span>
                <span className="font-mono font-bold text-blue-600">{confidenceThreshold.toFixed(1)}</span>
              </div>
              <Slider
                min={0.2}
                max={1.0}
                step={0.05}
                value={confidenceThreshold}
                onChange={setConfidenceThreshold}
              />
            </div>
          )}
        </div>

        {/* 手动权重滑块 */}
        {strategy === 'manual' && (
          <div className="bg-slate-50 rounded-xl p-3 space-y-3">
            <div className="text-[9px] text-slate-400 flex items-center gap-1">
              <Info size={10} /> 权重将自动归一化到总和 1.0
            </div>
            {models.map((m) => {
              const icir = icirs[m.model_id] ?? 0;
              return (
                <div key={m.model_id}>
                  <div className="flex justify-between items-center mb-0.5">
                    <span className="text-[10px] font-bold text-slate-600 truncate max-w-[55%]">
                      {modelDisplayName(m)}
                    </span>
                    <span className="text-[10px] font-mono text-blue-600 font-black">
                      {((computedWeights[m.model_id] ?? 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                  <Slider
                    min={0}
                    max={100}
                    step={1}
                    value={Math.round((manualWeights[m.model_id] ?? 10) * 10) / 10}
                    onChange={(v) => setManualWeights({ ...manualWeights, [m.model_id]: v as number })}
                    className="!mb-1"
                  />
                  <div className="text-[8px] text-slate-400 font-mono">
                    ICIR: {icir.toFixed(3)}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* 预览摘要 */}
        <div className="bg-gradient-to-br from-blue-50/60 to-slate-50 rounded-xl p-3">
          <div className="flex items-center justify-between text-[10px] text-slate-500">
            <span className="font-bold text-slate-600">创建摘要</span>
            <span className="font-mono">{models.length} 个源模型</span>
          </div>
          <div className="mt-1.5 space-y-0.5 text-[10px] text-slate-500 font-mono">
            <div className="flex justify-between">
              <span>权重策略</span>
              <span className="font-bold text-blue-600">
                {strategy === 'equal' ? '等权' : strategy === 'icir' ? 'ICIR 加权' : '手动'}
              </span>
            </div>
            <div className="flex justify-between">
              <span>特征并集</span>
              <span>{new Set(models.flatMap((m) => (getMeta(m).feature_columns as string[]) || (getMeta(m).features as string[]) || [])).size} 维</span>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  );
};
