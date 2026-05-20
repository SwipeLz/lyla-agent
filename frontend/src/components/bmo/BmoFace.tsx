export type BmoExpression =
  | "idle"
  | "happy"
  | "sad"
  | "very_sad"
  | "excited"
  | "dizzy"
  | "rage"
  | "shock"
  | "crying";

interface BmoFaceProps {
  expression: BmoExpression;
  size?: number;
  className?: string;
}

const FILE_MAP: Record<BmoExpression, string> = {
  idle: "idle_face.svg",
  happy: "happy_face.svg",
  sad: "sad_face.svg",
  very_sad: "very_sad_face.svg",
  excited: "excited_face.svg",
  dizzy: "dizzy_face.svg",
  rage: "rage_face.svg",
  shock: "shock_face.svg",
  crying: "crying_facee.svg",
};

const LABEL_MAP: Record<BmoExpression, string> = {
  idle: "BMO sedang menunggu",
  happy: "BMO senang",
  sad: "BMO sedih",
  very_sad: "BMO sangat sedih",
  excited: "BMO bersemangat",
  dizzy: "BMO pusing",
  rage: "BMO marah",
  shock: "BMO terkejut",
  crying: "BMO menangis",
};

export function BmoFace({
  expression,
  size = 120,
  className = "",
}: BmoFaceProps) {
  return (
    <img
      src={`/bmo/${FILE_MAP[expression]}`}
      alt={LABEL_MAP[expression]}
      width={size}
      height={Math.round((size * 9) / 16)}
      className={`select-none ${className}`}
      draggable={false}
    />
  );
}
