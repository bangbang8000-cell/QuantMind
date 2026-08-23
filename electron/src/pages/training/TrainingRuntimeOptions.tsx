import React from 'react';
import { Select, Switch } from 'antd';
import { clsx } from 'clsx';
import { Server, Clock, Cpu } from 'lucide-react';

export interface TrainingRuntimeOptionsProps {
  trainingNodes: any[];
  selectedNode: string;
  onSelectNode: (id: string) => void;
  maxTimeMinutes: number;
  onMaxTimeChange: (v: number) => void;
  pauseOthers: boolean;
  onPauseOthersChange: (v: boolean) => void;
  disabled?: boolean;
}

/**
 * 训练运行时选项（训练节点 / 时长预算 / 容器资源）。
 * 放在第 4 步「执行训练」页面右侧，避免长期占用左栏空间。
 */
export const TrainingRuntimeOptions: React.FC<TrainingRuntimeOptionsProps> = ({
  trainingNodes,
  selectedNode,
  onSelectNode,
  maxTimeMinutes,
  onMaxTimeChange,
  pauseOthers,
  onPauseOthersChange,
  disabled = false,
}) => {
  return (
    <div className="space-y-3">
      <div className="rounded-2xl bg-white border border-slate-200 p-4 shadow-sm">
        <div className="flex items-center gap-1.5 text-[10px] uppercase font-bold text-slate-400 mb-2">
          <Server size={12} />
          训练节点
        </div>
        <div className="flex gap-2">
          {trainingNodes.length > 0
            ? trainingNodes.map((n) => (
                <button
                  key={n.id}
                  disabled={disabled}
                  onClick={() => onSelectNode(n.id)}
                  className={clsx(
                    'flex-1 rounded-lg px-2 py-1.5 text-xs font-semibold border transition-all disabled:opacity-50',
                    selectedNode === n.id
                      ? n.type === 'remote'
                        ? 'bg-orange-50 border-orange-300 text-orange-700'
                        : 'bg-blue-50 border-blue-300 text-blue-700'
                      : 'bg-white border-gray-200 text-gray-500 hover:border-gray-300'
                  )}
                >
                  {n.name}
                </button>
              ))
            : <div className="text-[11px] text-slate-400 w-full text-center py-1">仅本地训练</div>}
        </div>
        {selectedNode !== 'local' && (
          <div className="mt-2 text-[10px] text-orange-600 leading-relaxed">
            将推送特征快照到 AutoDL，远程 GPU 训练完成后模型自动回传本机。
          </div>
        )}
      </div>

      <div className="rounded-2xl bg-white border border-slate-200 p-4 shadow-sm">
        <div className="flex items-center gap-1.5 text-[10px] uppercase font-bold text-slate-400 mb-2">
          <Clock size={12} />
          训练时长预算
        </div>
        <Select
          size="small"
          value={maxTimeMinutes}
          onChange={(v: number) => onMaxTimeChange(v)}
          disabled={disabled}
          style={{ width: '100%' }}
          options={[
            { value: 60, label: '1 小时（快速验证）' },
            { value: 120, label: '2 小时（默认）' },
            { value: 360, label: '6 小时' },
            { value: 720, label: '12 小时（DL 模型推荐）' },
            { value: 1440, label: '24 小时（上限）' },
          ]}
        />
        <div className="mt-1.5 text-[10px] text-slate-400 leading-relaxed">
          超过预算编排器会终止任务。GRU/LSTM 等 DL 模型在本地 CPU 训练较慢，请选择 12 小时或使用 GPU 节点。
        </div>
      </div>

      <div className="rounded-2xl bg-white border border-slate-200 p-4 shadow-sm">
        <div className="flex items-center gap-1.5 text-[10px] uppercase font-bold text-slate-400 mb-2">
          <Cpu size={12} />
          训练资源
        </div>
        <div className="flex items-center justify-between gap-3">
          <div className="flex flex-col min-w-0">
            <span className="text-xs font-bold text-slate-700">训练时关闭其他 Docker 容器</span>
            <span className="text-[10px] text-slate-400 leading-relaxed">
              开启=停掉其他容器释放内存给训练（默认）；关闭=保留其他容器运行
            </span>
          </div>
          <Switch
            size="small"
            checked={pauseOthers}
            onChange={onPauseOthersChange}
            disabled={disabled}
            checkedChildren="关闭"
            unCheckedChildren="保留"
          />
        </div>
        {selectedNode !== 'local' && (
          <div className="mt-1.5 text-[10px] text-orange-600 leading-relaxed">
            AutoDL 远程 GPU 节点不占用本机内存，此开关对本机容器无影响。
          </div>
        )}
      </div>
    </div>
  );
};
