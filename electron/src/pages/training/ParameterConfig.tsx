import React from 'react';
import { Card, Divider, Input, Button, Row, Col, InputNumber, Select, Alert, Typography, Tag, Checkbox, Switch, Tooltip } from 'antd';
import { Settings2, MonitorPlay, TreePine, Cpu, Ruler, AlertTriangle } from 'lucide-react';
import {
  TrainingParams,
  TrainingContext,
  DealPrice,
  ModelType,
  ModelCategory,
  ModelTypeOption,
  MODEL_TYPE_OPTIONS,
  EnsembleMethod,
  MODEL_DL_DEFAULTS,
} from './trainingUtils';
import type { AppMarket } from '../../store/slices/uiSlice';

const MARKET_BENCHMARKS: Record<string, { label: string; value: string }[]> = {
  CN: [
    { label: '沪深300', value: 'SH000300' },
    { label: '中证500', value: 'SH000905' },
    { label: '中证1000', value: 'SH000852' },
  ],
  HK: [
    { label: '恒生指数', value: 'HSI' },
    { label: '恒生国企', value: 'HSCEI' },
    { label: '恒生科技', value: 'HSTECH' },
  ],
  US: [
    { label: '标普500', value: 'SPX' },
    { label: '纳斯达克100', value: 'NDX' },
    { label: '道琼斯30', value: 'DJI' },
  ],
  CRYPTO: [
    { label: '比特币', value: 'BTC' },
    { label: '以太坊', value: 'ETH' },
  ],
};

interface ParameterConfigProps {
  params: TrainingParams;
  context: TrainingContext;
  onParamsChange: (params: TrainingParams) => void;
  onContextChange: (context: TrainingContext) => void;
  displayName: string;
  onDisplayNameChange: (name: string, mode: 'auto' | 'manual') => void;
  autoDisplayName: string;
  market?: AppMarket;
}

const SectionHeader: React.FC<{ title: string; desc: string; icon?: React.ReactNode }> = ({ title, desc, icon }) => (
  <div className="flex items-start justify-between gap-4">
    <div>
      <div className="flex items-center gap-2">
        {icon}
        <Typography.Title level={4} className="!mb-0 !text-slate-900">
          {title}
        </Typography.Title>
      </div>
      <Typography.Paragraph className="!mb-0 !mt-2 !text-xs !text-slate-500 leading-relaxed">
        {desc}
      </Typography.Paragraph>
    </div>
  </div>
);

export const ParameterConfig: React.FC<ParameterConfigProps> = ({
  params,
  context,
  onParamsChange,
  onContextChange,
  displayName,
  onDisplayNameChange,
  autoDisplayName,
  market = 'CN',
}) => {
  const benchmarkOptions = MARKET_BENCHMARKS[market] || MARKET_BENCHMARKS.CN;
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_0.9fr]">
      <Card className="rounded-3xl border-slate-200 shadow-sm" styles={{ body: { padding: 20 } }}>
        <SectionHeader
          title="第三步：参数配置"
          desc="把模型超参与训练上下文拆开，避免配置语义混在一起。"
          icon={<Settings2 size={18} className="text-indigo-500" />}
        />
        <Divider className="my-4" />
        <div className="space-y-4">
          {/* 模型类型选择 */}
          <Card className="rounded-2xl border-slate-200" size="small" title="模型类型">
            <div className="space-y-3">
              <div className="text-xs text-slate-500">
                选择训练模型。树模型适合快速实验，线性模型作为基线 sanity check，深度学习模型在大数据集上潜力更大。支持多选进行集成训练。
              </div>
              <Checkbox.Group
                value={params.model_types}
                className="w-full"
                onChange={(checkedValues) => {
                  const selected = checkedValues as ModelType[];
                  if (selected.length === 0) return;
                  const primary = selected[0];
                  // 切换模型类型时，自动填充该模型的推荐 DL 默认参数
                  const dlDefaults = MODEL_DL_DEFAULTS[primary] || {};
                  // 对于非 DL 模型，不覆盖已设置的 DL 参数
                  const updated: TrainingParams = {
                    ...params,
                    model_type: primary,
                    model_types: selected,
                    ensemble_method: selected.length > 1 ? (params.ensemble_method || 'none') : 'none',
                  };
                  if (dlDefaults.dl_hidden_size !== undefined) {
                    Object.assign(updated, dlDefaults);
                  }
                  onParamsChange(updated);
                }}
              >
                <div className="space-y-3">
                  <div className="text-xs font-medium text-slate-600 flex items-center gap-1">
                    <TreePine size={12} /> 树模型
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 pl-1">
                    {MODEL_TYPE_OPTIONS.filter(m => m.category === 'tree').map(m => (
                      <Checkbox key={m.value} value={m.value}>
                        <Tooltip title={m.tooltip} placement="topLeft" overlayStyle={{ maxWidth: 360 }}>
                          <span className="text-sm cursor-help border-b border-dashed border-slate-300">{m.label}</span>
                        </Tooltip>
                        <span className="text-xs text-slate-400 ml-1">{m.description}</span>
                      </Checkbox>
                    ))}
                  </div>
                  <div className="text-xs font-medium text-slate-600 flex items-center gap-1">
                    <Ruler size={12} /> 线性基线
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 pl-1">
                    {MODEL_TYPE_OPTIONS.filter(m => m.category === 'linear').map(m => (
                      <Checkbox key={m.value} value={m.value}>
                        <Tooltip title={m.tooltip} placement="topLeft" overlayStyle={{ maxWidth: 360 }}>
                          <span className="text-sm cursor-help border-b border-dashed border-slate-300">{m.label}</span>
                        </Tooltip>
                        <span className="text-xs text-slate-400 ml-1">{m.description}</span>
                      </Checkbox>
                    ))}
                  </div>
                  <div className="text-xs font-medium text-slate-600 flex items-center gap-1">
                    <Cpu size={12} /> 深度学习
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 pl-1">
                    {MODEL_TYPE_OPTIONS.filter(m => m.category === 'deep_learning').map(m => (
                      <Checkbox key={m.value} value={m.value}>
                        <Tooltip title={m.tooltip} placement="topLeft" overlayStyle={{ maxWidth: 360 }}>
                          <span className="text-sm cursor-help border-b border-dashed border-slate-300">{m.label}</span>
                        </Tooltip>
                        <span className="text-xs text-slate-400 ml-1">{m.description}</span>
                      </Checkbox>
                    ))}
                  </div>
                </div>
              </Checkbox.Group>
              {params.model_types.length > 1 && (
                <div className="flex flex-wrap gap-1.5">
                  {params.model_types.map(mt => {
                    const opt = MODEL_TYPE_OPTIONS.find(m => m.value === mt);
                    return (
                      <Tag key={mt} color="blue" className="rounded-lg">
                        {opt?.label ?? mt}
                      </Tag>
                    );
                  })}
                </div>
              )}
              {params.model_types.length > 1 && (() => {
                const hasTree = params.model_types.some(mt => {
                  const opt = MODEL_TYPE_OPTIONS.find(m => m.value === mt);
                  return opt?.category === 'tree' || opt?.category === 'linear';
                });
                const hasDL = params.model_types.some(mt => {
                  const opt = MODEL_TYPE_OPTIONS.find(m => m.value === mt);
                  return opt?.category === 'deep_learning';
                });
                return hasTree && hasDL;
              })() && (
                <Alert
                  type="warning"
                  showIcon
                  icon={<AlertTriangle size={14} />}
                  message="树模型与深度学习模型混合训练时，集成方法暂不支持，将分别独立训练"
                  className="rounded-xl"
                />
              )}
              {params.model_types.length > 1 && !(() => {
                const hasTree = params.model_types.some(mt => {
                  const opt = MODEL_TYPE_OPTIONS.find(m => m.value === mt);
                  return opt?.category === 'tree' || opt?.category === 'linear';
                });
                const hasDL = params.model_types.some(mt => {
                  const opt = MODEL_TYPE_OPTIONS.find(m => m.value === mt);
                  return opt?.category === 'deep_learning';
                });
                return hasTree && hasDL;
              })() && (
                <div className="space-y-1">
                  <div className="text-xs text-slate-500">集成方法</div>
                  <Select
                    value={params.ensemble_method}
                    className="w-full"
                    onChange={(value) => onParamsChange({ ...params, ensemble_method: value as EnsembleMethod })}
                    options={[
                      { label: '无集成 (各自独立训练)', value: 'none' },
                      { label: 'Stacking 集成', value: 'stacking' },
                    ]}
                  />
                </div>
              )}
              {params.model_types.some(mt => {
                const opt = MODEL_TYPE_OPTIONS.find(m => m.value === mt);
                return opt?.category === 'deep_learning';
              }) && (
                <Alert
                  type="info"
                  showIcon
                  message="深度学习模型需要 GPU 和 PyTorch 环境，训练时间较长"
                  className="rounded-xl"
                />
              )}
            </div>
          </Card>

          <Card className="rounded-2xl border-slate-200" size="small" title="模型命名">
            <div className="space-y-2">
              <div className="text-xs text-slate-500">
                display_name 用于模型管理页展示和训练结果命名，自动规则为“日期_T+N_模型维度_版本”。
              </div>
              <div className="flex gap-2">
                <Input
                  value={displayName}
                  onChange={(event) => onDisplayNameChange(event.target.value, 'manual')}
                  placeholder={autoDisplayName}
                  className="rounded-xl"
                  maxLength={128}
                />
                <Button
                  className="rounded-xl"
                  onClick={() => onDisplayNameChange(autoDisplayName, 'auto')}
                >
                  恢复自动
                </Button>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400">
                <span>当前自动示例：{autoDisplayName}</span>
                <span>{displayName.trim().length}/128</span>
              </div>
            </div>
          </Card>

          <Card className="rounded-2xl border-slate-200" size="small" title="训练超参">
            <div className="space-y-4">
              {/* Objective & Metric - 共享 */}
              <Row gutter={[12, 12]}>
                <Col span={12}>
                  <div className="space-y-1">
                    <div className="text-xs text-slate-500">Objective</div>
                    <Select
                      value={params.objective}
                      className="w-full"
                      onChange={(value) => onParamsChange({ ...params, objective: value as TrainingParams['objective'] })}
                      options={[
                        { label: '回归 (regression)', value: 'regression' },
                        { label: '二分类 (binary)', value: 'binary' },
                      ]}
                    />
                  </div>
                </Col>
                <Col span={12}>
                  <div className="space-y-1">
                    <div className="text-xs text-slate-500">Metric</div>
                    <Select
                      value={params.metric}
                      className="w-full"
                      onChange={(value) => onParamsChange({ ...params, metric: value as TrainingParams['metric'] })}
                      options={[
                        { label: 'L2', value: 'l2' },
                        { label: 'RMSE', value: 'rmse' },
                        { label: 'MAE', value: 'mae' },
                        { label: 'AUC', value: 'auc' },
                        { label: 'Binary Logloss', value: 'binary_logloss' },
                      ]}
                    />
                  </div>
                </Col>
              </Row>

              {/* LightGBM 专属参数 */}
              {params.model_types.includes('lightgbm') && (
                <>
                  <div className="text-xs font-medium text-slate-500 border-t pt-3">LightGBM 超参</div>
                  <Row gutter={[12, 12]}>
                    {[
                      ['num_leaves', '叶子数', { min: 1, max: 1024, step: 1 }],
                      ['min_data_in_leaf', '叶子最小样本', { min: 1, max: 10000, step: 1 }],
                      ['lambda_l1', 'L1 正则', { min: 0, max: 10, step: 0.1 }],
                      ['lambda_l2', 'L2 正则', { min: 0, max: 10, step: 0.1 }],
                      ['feature_fraction', '特征采样', { min: 0.1, max: 1, step: 0.01 }],
                      ['bagging_fraction', '行采样', { min: 0.1, max: 1, step: 0.01 }],
                      ['num_boost_round', '最大迭代轮数', { min: 1, max: 10000, step: 10 }],
                      ['early_stopping_rounds', '早停轮数', { min: 1, max: 1000, step: 5 }],
                    ].map(([key, label, lim]) => (
                      <Col span={12} key={key as string}>
                        <div className="space-y-1">
                          <div className="text-xs text-slate-500">{label as string}</div>
                          <InputNumber
                            value={params[key as keyof TrainingParams] as number}
                            min={(lim as any)?.min}
                            max={(lim as any)?.max}
                            step={(lim as any)?.step}
                            className="w-full"
                            onChange={(v) => onParamsChange({ ...params, [key as string]: Number(v ?? params[key as keyof TrainingParams]) })}
                          />
                        </div>
                      </Col>
                    ))}
                    <Col span={12}>
                      <div className="space-y-1">
                        <div className="text-xs text-slate-500">学习率 (lgb_learning_rate)</div>
                        <InputNumber
                          value={params.lgb_learning_rate ?? params.learning_rate}
                          min={0.0001}
                          max={1}
                          step={0.001}
                          className="w-full"
                          onChange={(v) => onParamsChange({ ...params, lgb_learning_rate: Number(v ?? params.learning_rate) })}
                        />
                      </div>
                    </Col>
                    <Col span={12}>
                      <div className="space-y-1">
                        <div className="text-xs text-slate-500">最大深度 (lgb_max_depth)</div>
                        <InputNumber
                          value={params.lgb_max_depth ?? params.max_depth}
                          min={-1}
                          max={64}
                          step={1}
                          className="w-full"
                          onChange={(v) => onParamsChange({ ...params, lgb_max_depth: Number(v ?? params.max_depth) })}
                        />
                      </div>
                    </Col>
                  </Row>
                </>
              )}

              {/* XGBoost 专属参数 */}
              {params.model_types.includes('xgboost') && (
                <>
                  <div className="text-xs font-medium text-slate-500 border-t pt-3">XGBoost 超参</div>
                  <Row gutter={[12, 12]}>
                    {[
                      ['xgb_subsample', '行采样 (subsample)', { min: 0.1, max: 1, step: 0.05 }],
                      ['xgb_colsample_bytree', '列采样', { min: 0.1, max: 1, step: 0.05 }],
                      ['xgb_reg_alpha', 'L1 正则', { min: 0, max: 10, step: 0.1 }],
                      ['xgb_reg_lambda', 'L2 正则', { min: 0, max: 10, step: 0.1 }],
                      ['num_boost_round', '最大迭代轮数', { min: 1, max: 10000, step: 10 }],
                      ['early_stopping_rounds', '早停轮数', { min: 1, max: 1000, step: 5 }],
                    ].map(([key, label, lim]) => (
                      <Col span={12} key={key as string}>
                        <div className="space-y-1">
                          <div className="text-xs text-slate-500">{label as string}</div>
                          <InputNumber
                            value={params[key as keyof TrainingParams] as number}
                            min={(lim as any)?.min}
                            max={(lim as any)?.max}
                            step={(lim as any)?.step}
                            className="w-full"
                            onChange={(v) => onParamsChange({ ...params, [key as string]: Number(v ?? params[key as keyof TrainingParams]) })}
                          />
                        </div>
                      </Col>
                    ))}
                    <Col span={12}>
                      <div className="space-y-1">
                        <div className="text-xs text-slate-500">学习率 (xgb_learning_rate)</div>
                        <InputNumber
                          value={params.xgb_learning_rate ?? params.learning_rate}
                          min={0.0001}
                          max={1}
                          step={0.001}
                          className="w-full"
                          onChange={(v) => onParamsChange({ ...params, xgb_learning_rate: Number(v ?? params.learning_rate) })}
                        />
                      </div>
                    </Col>
                    <Col span={12}>
                      <div className="space-y-1">
                        <div className="text-xs text-slate-500">最大深度 (xgb_max_depth)</div>
                        <InputNumber
                          value={params.xgb_max_depth ?? params.max_depth}
                          min={1}
                          max={16}
                          step={1}
                          className="w-full"
                          onChange={(v) => onParamsChange({ ...params, xgb_max_depth: Number(v ?? params.max_depth) })}
                        />
                      </div>
                    </Col>
                  </Row>
                </>
              )}

              {/* CatBoost 专属参数 */}
              {params.model_types.includes('catboost') && (
                <>
                  <div className="text-xs font-medium text-slate-500 border-t pt-3">CatBoost 超参</div>
                  <Row gutter={[12, 12]}>
                    {[
                      ['cb_l2_leaf_reg', 'L2 正则', { min: 0, max: 10, step: 0.5 }],
                      ['cb_random_strength', '随机扰动', { min: 0, max: 10, step: 0.5 }],
                      ['cb_bagging_temperature', 'Bagging 温度', { min: 0, max: 10, step: 0.5 }],
                      ['num_boost_round', '最大迭代轮数', { min: 1, max: 10000, step: 10 }],
                      ['early_stopping_rounds', '早停轮数', { min: 1, max: 1000, step: 5 }],
                    ].map(([key, label, lim]) => (
                      <Col span={12} key={key as string}>
                        <div className="space-y-1">
                          <div className="text-xs text-slate-500">{label as string}</div>
                          <InputNumber
                            value={params[key as keyof TrainingParams] as number}
                            min={(lim as any)?.min}
                            max={(lim as any)?.max}
                            step={(lim as any)?.step}
                            className="w-full"
                            onChange={(v) => onParamsChange({ ...params, [key as string]: Number(v ?? params[key as keyof TrainingParams]) })}
                          />
                        </div>
                      </Col>
                    ))}
                    <Col span={12}>
                      <div className="space-y-1">
                        <div className="text-xs text-slate-500">学习率 (cb_learning_rate)</div>
                        <InputNumber
                          value={params.cb_learning_rate ?? params.learning_rate}
                          min={0.001}
                          max={1}
                          step={0.01}
                          className="w-full"
                          onChange={(v) => onParamsChange({ ...params, cb_learning_rate: Number(v ?? params.learning_rate) })}
                        />
                      </div>
                    </Col>
                    <Col span={12}>
                      <div className="space-y-1">
                        <div className="text-xs text-slate-500">树深度 (cb_depth)</div>
                        <InputNumber
                          value={params.cb_depth ?? params.max_depth}
                          min={1}
                          max={16}
                          step={1}
                          className="w-full"
                          onChange={(v) => onParamsChange({ ...params, cb_depth: Number(v ?? params.max_depth) })}
                        />
                      </div>
                    </Col>
                  </Row>
                </>
              )}

              {/* Linear 专属参数 */}
              {params.model_types.includes('linear') && (
                <>
                  <div className="text-xs font-medium text-slate-500 border-t pt-3">Ridge 回归超参</div>
                  <Row gutter={[12, 12]}>
                    <Col span={12}>
                      <div className="space-y-1">
                        <div className="text-xs text-slate-500">正则化系数 (alpha)</div>
                        <InputNumber
                          value={params.linear_alpha ?? 1.0}
                          min={0.0001}
                          max={1000}
                          step={0.1}
                          className="w-full"
                          onChange={(v) => onParamsChange({ ...params, linear_alpha: Number(v ?? 1.0) })}
                        />
                      </div>
                    </Col>
                  </Row>
                </>
              )}

              {/* 深度学习模型参数 */}
              {params.model_types.some(mt => {
                const opt = MODEL_TYPE_OPTIONS.find(m => m.value === mt);
                return opt?.category === 'deep_learning';
              }) && (
                <>
                  <div className="text-xs font-medium text-slate-500 border-t pt-3">
                    深度学习超参 (主模型: {params.model_type ?
                      MODEL_TYPE_OPTIONS.find(m => m.value === params.model_type)?.label :
                      params.model_types.filter(mt => {
                        const opt = MODEL_TYPE_OPTIONS.find(m => m.value === mt);
                        return opt?.category === 'deep_learning';
                      }).map(mt => MODEL_TYPE_OPTIONS.find(m => m.value === mt)?.label).join(', ')}
                    )
                    <span className="ml-2 text-slate-400">— 切换模型时自动填充推荐默认值</span>
                  </div>
                  <Row gutter={[12, 12]}>
                    {[
                      ['dl_hidden_size', '隐藏维度', { min: 16, max: 512, step: 16 }],
                      ['dl_num_layers', '网络层数', { min: 1, max: 8, step: 1 }],
                      ['dl_dropout', 'Dropout', { min: 0, max: 0.9, step: 0.05 }],
                      ['dl_n_epochs', '训练轮数', { min: 10, max: 1000, step: 10 }],
                      ['dl_batch_size', 'Batch Size', { min: 64, max: 10000, step: 64 }],
                      ['dl_lr', '学习率', { min: 0.00001, max: 0.1, step: 0.0001 }],
                      ['dl_step_len', '序列长度', { min: 5, max: 120, step: 5 }],
                    ].map(([key, label, lim]) => (
                      <Col span={12} key={key as string}>
                        <div className="space-y-1">
                          <div className="text-xs text-slate-500">{label as string}</div>
                          <InputNumber
                            value={params[key as keyof TrainingParams] as number}
                            min={(lim as any)?.min}
                            max={(lim as any)?.max}
                            step={(lim as any)?.step}
                            className="w-full"
                            onChange={(v) => onParamsChange({ ...params, [key as string]: Number(v ?? params[key as keyof TrainingParams]) })}
                          />
                        </div>
                      </Col>
                    ))}
                  </Row>
                </>
              )}
            </div>
          </Card>

        </div>
      </Card>

      <Card className="rounded-3xl border-slate-200 shadow-sm" styles={{ body: { padding: 20 } }}>
        <SectionHeader
          title="训练上下文"
          desc="记录训练时的资产、基准与交易成本，方便后续回放与模型管理页对齐。"
          icon={<MonitorPlay size={18} className="text-indigo-500" />}
        />
        <Divider className="my-4" />
        <div className="space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <div className="mb-1 text-xs text-slate-500">初始资金</div>
                <InputNumber
                  value={context.initialCapital}
                  min={1000}
                  step={10000}
                  className="w-full"
                  onChange={(value) => onContextChange({ ...context, initialCapital: Number(value ?? context.initialCapital) })}
                />
              </div>
              <div>
                <div className="mb-1 text-xs text-slate-500">基准指数</div>
                <Select
                  value={context.benchmark}
                  className="w-full"
                  onChange={(value) => onContextChange({ ...context, benchmark: value })}
                  options={benchmarkOptions}
                />
              </div>
              <div>
                <div className="mb-1 text-xs text-slate-500">手续费率</div>
                <InputNumber
                  value={context.commissionRate}
                  min={0}
                  max={1}
                  step={0.0001}
                  className="w-full"
                  onChange={(value) => onContextChange({ ...context, commissionRate: Number(value ?? context.commissionRate) })}
                />
              </div>
              <div>
                <div className="mb-1 text-xs text-slate-500">滑点</div>
                <InputNumber
                  value={context.slippage}
                  min={0}
                  max={1}
                  step={0.0001}
                  className="w-full"
                  onChange={(value) => onContextChange({ ...context, slippage: Number(value ?? context.slippage) })}
                />
              </div>
              <div className="md:col-span-2">
                <div className="mb-1 text-xs text-slate-500">成交价格</div>
                <Select
                  value={context.dealPrice}
                  className="w-full"
                  onChange={(value) => onContextChange({ ...context, dealPrice: value as DealPrice })}
                  options={[
                    { label: '开盘价 (open)', value: 'open' },
                    { label: '收盘价 (close)', value: 'close' },
                  ]}
                />
              </div>
              <div className="md:col-span-2 flex items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2">
                <div className="space-y-0.5">
                  <div className="text-xs text-slate-500">行业编码作为特征</div>
                  <div className="text-[11px] text-slate-400">
                    将行业编码作为特征加入模型，CatBoost 原生支持类别特征
                  </div>
                </div>
                <Tooltip title="将行业编码作为特征加入模型，CatBoost原生支持类别特征">
                  <Switch
                    checked={!!context.industry_as_feature}
                    onChange={(checked) => onContextChange({ ...context, industry_as_feature: checked })}
                  />
                </Tooltip>
              </div>
            </div>
          </div>

          <Alert
            type="warning"
            showIcon
            message="口径提醒"
            description="训练上下文会写入请求预览和模型元数据，保证模型管理页、回测中心和训练页使用同一套参数口径。"
            className="rounded-2xl border-amber-100 bg-amber-50/70"
          />
        </div>
      </Card>
    </div>
  );
};
