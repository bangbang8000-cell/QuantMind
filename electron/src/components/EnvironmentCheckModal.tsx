/**
 * 环境检测弹窗组件
 * 用于检测系统环境和硬件配置
 */
import React, { useState, useEffect } from 'react';
import {
  X,
  CheckCircle,
  XCircle,
  Loader2,
  Monitor,
  Cpu,
  HardDrive,
  AlertCircle,
  ChevronRight
} from 'lucide-react';
import axios from 'axios';
import { SERVICE_ENDPOINTS } from '../config/services';

interface EnvironmentCheckModalProps {
  isOpen: boolean;
  onClose: () => void;
  onComplete?: (config: any) => void;
}

interface DetectionResult {
  is_valid: boolean;
  message: string;
  [key: string]: any;
}

interface StepData {
  system?: DetectionResult;
  cpu?: DetectionResult;
  memory?: DetectionResult;
}

type Step = 'detection' | 'complete';

export const EnvironmentCheckModal: React.FC<EnvironmentCheckModalProps> = ({
  isOpen,
  onClose,
  onComplete
}) => {
  const [step, setStep] = useState<Step>('detection');
  const [loading, setLoading] = useState(false);
  const [stepData, setStepData] = useState<StepData>({});

  const API_BASE = `${SERVICE_ENDPOINTS.TRADING}/environment`;

  useEffect(() => {
    if (isOpen && step === 'detection') {
      performDetection();
    }
  }, [isOpen, step]);

  const performDetection = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API_BASE}/detect/all`);
      const data = response.data.data;

      setStepData({
        system: data.system,
        cpu: data.cpu,
        memory: data.memory,
      });

      if (data.success) {
        setTimeout(() => {
          setStep('complete');
        }, 1500);
      }
    } catch (error) {
      console.error('环境检测失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleComplete = () => {
    if (onComplete) {
      onComplete({});
    }
    onClose();
  };

  const renderDetectionItem = (
    icon: React.ReactNode,
    title: string,
    data?: DetectionResult
  ) => {
    if (!data) {
      return (
        <div className="flex items-center space-x-3 p-4 bg-gray-50 rounded-lg">
          {icon}
          <div className="flex-1">
            <div className="font-medium text-gray-700">{title}</div>
            <div className="text-sm text-gray-500">检测中...</div>
          </div>
          <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
        </div>
      );
    }

    return (
      <div className={`flex items-center space-x-3 p-4 rounded-lg ${
        data.is_valid ? 'bg-green-50' : 'bg-red-50'
      }`}>
        {icon}
        <div className="flex-1">
          <div className="font-medium text-gray-700">{title}</div>
          <div className={`text-sm ${data.is_valid ? 'text-green-600' : 'text-red-600'}`}>
            {data.message}
          </div>
        </div>
        {data.is_valid ? (
          <CheckCircle className="w-5 h-5 text-green-500" />
        ) : (
          <XCircle className="w-5 h-5 text-red-500" />
        )}
      </div>
    );
  };

  const renderDetectionStep = () => (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-gray-800 mb-4">
        环境检测
      </h3>

      {renderDetectionItem(
        <Monitor className="w-6 h-6 text-blue-500" />,
        '系统环境',
        stepData.system
      )}

      {renderDetectionItem(
        <Cpu className="w-6 h-6 text-blue-500" />,
        'CPU配置',
        stepData.cpu
      )}

      {renderDetectionItem(
        <HardDrive className="w-6 h-6 text-blue-500" />,
        '内存配置',
        stepData.memory
      )}

      {stepData.system && !loading && (
        <div className="pt-4">
          {stepData.system.is_valid &&
           stepData.cpu?.is_valid &&
           stepData.memory?.is_valid ? (
            <div className="text-center text-green-600">
              <CheckCircle className="w-12 h-12 mx-auto mb-2" />
              <p>所有检测项通过！</p>
            </div>
          ) : (
            <div className="text-center">
              <AlertCircle className="w-12 h-12 mx-auto mb-2 text-red-500" />
              <p className="text-red-600">部分检测项未通过</p>
              <button
                onClick={performDetection}
                className="mt-3 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                重新检测
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );

  const renderCompleteStep = () => (
    <div className="space-y-4 text-center py-8">
      <CheckCircle className="w-16 h-16 mx-auto text-green-500" />
      <h3 className="text-lg font-semibold text-gray-800">
        配置完成！
      </h3>
      <p className="text-gray-600">
        环境检测通过，配置已保存
      </p>

      <button
        onClick={handleComplete}
        className="w-full px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
      >
        完成
      </button>
    </div>
  );

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b">
          <h2 className="text-xl font-bold text-gray-800">环境检测</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="w-6 h-6 text-gray-500" />
          </button>
        </div>

        <div className="flex items-center justify-center space-x-2 p-4 bg-gray-50">
          <div className={`flex items-center ${step === 'detection' ? 'text-blue-600' : 'text-gray-400'}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
              step === 'detection' ? 'bg-blue-600 text-white' : 'bg-gray-200'
            }`}>
              1
            </div>
            <span className="ml-2 text-sm font-medium">环境检测</span>
          </div>

          <ChevronRight className="w-5 h-5 text-gray-400" />

          <div className={`flex items-center ${step === 'complete' ? 'text-blue-600' : 'text-gray-400'}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
              step === 'complete' ? 'bg-blue-600 text-white' : 'bg-gray-200'
            }`}>
              2
            </div>
            <span className="ml-2 text-sm font-medium">完成</span>
          </div>
        </div>

        <div className="p-6">
          {step === 'detection' && renderDetectionStep()}
          {step === 'complete' && renderCompleteStep()}
        </div>
      </div>
    </div>
  );
};
