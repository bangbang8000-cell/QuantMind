import { apiClient } from './api-client';

export interface SystemCapabilities {
  edition: 'oss' | 'enterprise';
  features: {
    sms: boolean;
    cos: boolean;
    multi_strategy: boolean;
    advanced_factors: boolean;
    rbac_enhanced: boolean;
    audit_logs: boolean;
    local_storage: boolean;
    k8s_deployment: boolean;
  };
}

export interface SystemVersion {
  version: string;
  edition: 'oss' | 'enterprise';
}

export const systemService = {
  /**
   * 获取系统能力与版本信息
   */
  getCapabilities: async (): Promise<SystemCapabilities> => {
    return apiClient.get<SystemCapabilities>('/api/v1/system/capabilities');
  },

  /**
   * 获取当前运行代码版本（deploy/update.sh 更新后由 version.txt 写入）
   */
  getVersion: async (): Promise<SystemVersion> => {
    return apiClient.get<SystemVersion>('/api/v1/system/version');
  }
};
