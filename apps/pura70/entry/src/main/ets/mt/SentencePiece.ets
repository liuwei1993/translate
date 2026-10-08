interface PieceRec {
  p: string;
  s: number;
  id: number;
}

interface TokFile {
  unkScore: number;
  unkId: number;
  eosId: number;
  padId: number;
  pieces: PieceRec[];
  decode: string[];
}

class PathNode {
  score: number = -1e30;
  prev: number = -1;
  id: number = 1;
  text: string = '';
}

export class SentencePieceTokenizer {
  unkScore: number = 0;
  unkId: number = 1;
  eosId: number = 0;
  padId: number = 65000;
  private buckets: Map<string, PieceRec[]> = new Map();
  private decodeTable: string[] = [];

  static fromJson(text: string): SentencePieceTokenizer {
    const file = JSON.parse(text) as TokFile;
    const tokenizer = new SentencePieceTokenizer();
    tokenizer.unkScore = file.unkScore;
    tokenizer.unkId = file.unkId;
    tokenizer.eosId = file.eosId;
    tokenizer.padId = file.padId;
    tokenizer.decodeTable = file.decode;
    for (let i = 0; i < file.pieces.length; i++) {
      const piece = file.pieces[i];
      const key = piece.p.substring(0, 1);
      let list = tokenizer.buckets.get(key);
      if (list === undefined) {
        list = [];
        tokenizer.buckets.set(key, list);
      }
      list.push(piece);
    }
    tokenizer.buckets.forEach((list: PieceRec[]) => {
      list.sort((a: PieceRec, b: PieceRec) => b.p.length - a.p.length);
    });
    return tokenizer;
  }

  encode(text: string): number[] {
    const normalized = `▁${text.trim().split(/\s+/).join(' ').replace(/ /g, '▁')}`;
    const nodes: PathNode[] = [];
    const count = normalized.length;
    for (let i = 0; i <= count; i++) {
      nodes.push(new PathNode());
    }
    nodes[0].score = 0;
    for (let i = 0; i < count; i++) {
      if (nodes[i].score < -1e20) {
        continue;
      }
      const list = this.buckets.get(normalized.substring(i, i + 1));
      let matched = false;
      if (list !== undefined) {
        for (let j = 0; j < list.length; j++) {
          const piece = list[j];
          const end = i + piece.p.length;
          if (end <= count && normalized.substring(i, end) === piece.p) {
            const score = nodes[i].score + piece.s;
            if (score > nodes[end].score) {
              nodes[end].score = score;
              nodes[end].prev = i;
              nodes[end].id = piece.id;
              nodes[end].text = piece.p;
            }
            matched = true;
          }
        }
      }
      if (!matched) {
        const score = nodes[i].score + this.unkScore;
        if (score > nodes[i + 1].score) {
          nodes[i + 1].score = score;
          nodes[i + 1].prev = i;
          nodes[i + 1].id = this.unkId;
          nodes[i + 1].text = normalized.substring(i, i + 1);
        }
      }
    }
    const ids: number[] = [];
    let cursor = count;
    if (nodes[count].prev < 0 && count > 0) {
      ids.push(this.unkId);
    } else {
      while (cursor > 0) {
        ids.push(nodes[cursor].id);
        cursor = nodes[cursor].prev;
      }
      ids.reverse();
    }
    ids.push(this.eosId);
    return ids;
  }

  decodeIds(ids: number[]): string {
    let text = '';
    for (let i = 0; i < ids.length; i++) {
      const id = ids[i];
      if (id === this.eosId || id === this.unkId || id === this.padId) {
        continue;
      }
      if (id >= 0 && id < this.decodeTable.length) {
        text += this.decodeTable[id];
      }
    }
    return text.replace(/▁/g, ' ').trim();
  }
}
