interface BmoMascotProps {
  size?: 28 | 48 | 80;
  className?: string;
}

const SIZE_CONFIG = {
  28: {
    body: { width: 28, height: 40, radius: 4 },
    face: { left: 3, top: 3, width: 22, height: 13, radius: 3 },
    eye: { width: 3, height: 4, top: 3, leftL: 5, leftR: 14 },
    disc: { left: 3, top: 19, width: 18, height: 2 },
    rbtn: { left: 15, top: 23, width: 6, height: 6 },
    bb1: { left: 3, top: 32, width: 8, height: 3 },
    bb2: { left: 13, top: 32, width: 8, height: 3 },
    showShadow: false,
    showMouth: false,
    showPlus: false,
    showGbtn: false,
  },
  48: {
    body: { width: 48, height: 68, radius: 6 },
    face: { left: 5, top: 5, width: 38, height: 23, radius: 4 },
    eye: { width: 5, height: 6, top: 6, leftL: 9, leftR: 24 },
    mouth: { left: 12, top: 14, width: 14, height: 7 },
    disc: { left: 4, top: 31, width: 30, height: 3 },
    plusV: { left: 6, top: 38, width: 4, height: 11 },
    plusH: { left: 3, top: 42, width: 12, height: 4 },
    rbtn: { left: 27, top: 38, width: 8, height: 8 },
    bb1: { left: 5, top: 54, width: 12, height: 4 },
    bb2: { left: 19, top: 54, width: 12, height: 4 },
    showShadow: true,
    showMouth: true,
    showPlus: true,
    showGbtn: false,
  },
  80: {
    body: { width: 80, height: 112, radius: 8 },
    face: { left: 8, top: 7, width: 64, height: 38, radius: 6 },
    eye: { width: 7, height: 9, top: 10, leftL: 16, leftR: 41 },
    mouth: { left: 19, top: 23, width: 26, height: 12 },
    disc: { left: 7, top: 52, width: 50, height: 5 },
    plusV: { left: 11, top: 64, width: 6, height: 18 },
    plusH: { left: 5, top: 70, width: 18, height: 6 },
    rbtn: { left: 44, top: 64, width: 12, height: 12 },
    gbtn: { left: 58, top: 64, width: 10, height: 10 },
    bb1: { left: 7, top: 88, width: 18, height: 6 },
    bb2: { left: 29, top: 88, width: 18, height: 6 },
    showShadow: true,
    showMouth: true,
    showPlus: true,
    showGbtn: true,
  },
} as const;

export function BmoMascot({ size = 80, className = "" }: BmoMascotProps) {
  const c = SIZE_CONFIG[size];
  return (
    <div
      role="img"
      aria-label="BMO mascot"
      className={`relative shrink-0 ${className}`}
      style={{
        width: c.body.width,
        height: c.body.height,
        background: "#9FD5B1",
        borderRadius: c.body.radius,
        boxShadow: c.showShadow ? "-2px 2px 0 2px #639975" : undefined,
      }}
    >
      <div
        className="absolute overflow-hidden"
        style={{
          left: c.face.left,
          top: c.face.top,
          width: c.face.width,
          height: c.face.height,
          background: "#C5E3BF",
          borderRadius: c.face.radius,
          boxShadow: "-1px 1px 1px rgba(147,177,141,1) inset",
        }}
      >
        <div
          className="absolute rounded-full bg-black"
          style={{
            width: c.eye.width,
            height: c.eye.height,
            top: c.eye.top,
            left: c.eye.leftL,
          }}
        />
        <div
          className="absolute rounded-full bg-black"
          style={{
            width: c.eye.width,
            height: c.eye.height,
            top: c.eye.top,
            left: c.eye.leftR,
          }}
        />
        {c.showMouth && "mouth" in c ? (
          <div
            className="absolute overflow-hidden"
            style={{
              left: c.mouth.left,
              top: c.mouth.top,
              width: c.mouth.width,
              height: c.mouth.height,
            }}
          >
            <div
              style={{
                width: c.mouth.width,
                height: c.mouth.height,
                background: "#1F8941",
                borderBottomLeftRadius: 700,
                borderBottomRightRadius: 700,
                borderTopLeftRadius: 320,
                borderTopRightRadius: 320,
              }}
            />
            <div
              className="absolute rounded-full"
              style={{
                background: "#C5E3BF",
                width: c.mouth.width + 6,
                height: c.mouth.height,
                top: -(c.mouth.height - 1),
                left: -3,
              }}
            />
          </div>
        ) : null}
      </div>
      <div
        className="absolute"
        style={{
          left: c.disc.left,
          top: c.disc.top,
          width: c.disc.width,
          height: c.disc.height,
          background: "#1C4B3B",
        }}
      />
      {c.showPlus && "plusV" in c ? (
        <>
          <div
            className="absolute"
            style={{
              left: c.plusV.left,
              top: c.plusV.top,
              width: c.plusV.width,
              height: c.plusV.height,
              background: "#F7E72F",
            }}
          />
          <div
            className="absolute"
            style={{
              left: c.plusH.left,
              top: c.plusH.top,
              width: c.plusH.width,
              height: c.plusH.height,
              background: "#F7E72F",
            }}
          />
        </>
      ) : null}
      <div
        className="absolute rounded-full"
        style={{
          left: c.rbtn.left,
          top: c.rbtn.top,
          width: c.rbtn.width,
          height: c.rbtn.height,
          background: "#ED306A",
        }}
      />
      {c.showGbtn && "gbtn" in c ? (
        <div
          className="absolute rounded-full"
          style={{
            left: c.gbtn.left,
            top: c.gbtn.top,
            width: c.gbtn.width,
            height: c.gbtn.height,
            background: "#74C042",
          }}
        />
      ) : null}
      <div
        className="absolute rounded"
        style={{
          left: c.bb1.left,
          top: c.bb1.top,
          width: c.bb1.width,
          height: c.bb1.height,
          background: "#313F98",
        }}
      />
      <div
        className="absolute rounded"
        style={{
          left: c.bb2.left,
          top: c.bb2.top,
          width: c.bb2.width,
          height: c.bb2.height,
          background: "#313F98",
        }}
      />
    </div>
  );
}
