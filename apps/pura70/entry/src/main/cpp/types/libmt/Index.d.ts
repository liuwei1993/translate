export const openModels: (name: string, encoderPath: string, decoderPath: string) => void;
export const translateIds: (name: string, ids: number[], padId: number, eosId: number) => number[];
export const closeModels: () => void;
