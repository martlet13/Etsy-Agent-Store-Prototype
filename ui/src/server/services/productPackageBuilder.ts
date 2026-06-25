export interface ProductPackageBuildInput {
  workItem?: any;
  novaResearch?: any;
  imageAsset?: any;
  sentinelReport?: any;
  supplierResearch?: any;
  ledgerResult?: any;
  scribeResult?: any;
  policy?: any;
}

export declare function buildProductPackage(input?: ProductPackageBuildInput): any;
export declare function saveProductPackage(pkg: any): any;
export declare function listProductPackages(): any[];
