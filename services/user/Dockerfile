# --- Giai đoạn Build ---
FROM node:20-alpine AS builder

WORKDIR /usr/src/app

COPY package*.json ./

RUN npm install

COPY . .

# Sinh Prisma Client động trước khi compile TypeScript
RUN npx prisma generate

RUN npm run build

# --- Giai đoạn Runtime ---
FROM node:20-alpine

WORKDIR /usr/src/app

COPY package*.json ./

# Chỉ cài đặt dependencies cho môi trường production
RUN npm install --only=production

# Copy mã nguồn đã build từ stage builder
COPY --from=builder /usr/src/app/dist ./dist
COPY --from=builder /usr/src/app/node_modules/.prisma ./node_modules/.prisma
COPY --from=builder /usr/src/app/proto ./proto

EXPOSE 3008
EXPOSE 50058

CMD ["node", "dist/src/main"]
