export interface EtsyPublishOptions {
  mode?: "dry_run" | "live";
}

export declare function getEtsyConnectorStatus(): any;
export declare function buildEtsyListingPayload(productPackage: any): any;
export declare function validateEtsyListingPayload(payload: any): any;
export declare function publishEtsyListing(productPackage: any, options?: EtsyPublishOptions): Promise<any>;
export declare function findProductPackage(packageId: string): any;
